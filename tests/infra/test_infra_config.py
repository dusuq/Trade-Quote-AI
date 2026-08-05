"""Infrastructure configuration test suite (T309 / M24).

Infra code fails differently from application code: a typo doesn't raise an
exception, it quietly deploys a service on the wrong port, or points Prometheus
at nothing, or ships an image running as root. None of that surfaces until
production. These tests are the gate that catches it in CI instead.

What's covered:
  - the service registry is well-formed and internally consistent
  - generated artifacts (Dockerfile/.dockerignore/fly.toml/targets) are in sync
    with infra/services.yml
  - the port map agrees across the registry, the gateway's own config, the
    Dockerfiles, the fly configs, and the Prometheus targets
  - container security posture: non-root, pinned bases, healthchecks
  - the monitoring stack is coherent: configs parse, every unit is probed,
    every alert is actionable, every referenced file actually exists

What is NOT covered, and cannot be here: whether the images actually BUILD.
That needs a Docker daemon, which this environment does not have. See
docs/12-PRODUCTION-RUNBOOK.md for what still needs live verification.

Run:  python -m pytest tests/infra -q
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY_PATH = REPO_ROOT / "infra" / "services.yml"
MONITORING = REPO_ROOT / "infra" / "monitoring"
GATEWAY_CONFIG_TS = REPO_ROOT / "apps" / "api-gateway" / "src" / "config.ts"


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def registry() -> dict[str, Any]:
    with REGISTRY_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="session")
def units(registry: dict[str, Any]) -> list[dict[str, Any]]:
    return registry["units"]


def _load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _unit_ids(units: list[dict[str, Any]]) -> list[str]:
    return [u["name"] for u in units]


@pytest.fixture(scope="session")
def alert_rules() -> list[dict[str, Any]]:
    """Every alert rule across all rule files, flattened."""
    collected: list[dict[str, Any]] = []
    for path in sorted((MONITORING / "prometheus" / "rules").glob("*.yml")):
        doc = _load_yaml(path)
        for group in doc["groups"]:
            for rule in group.get("rules", []):
                if "alert" in rule:
                    collected.append(rule)
    return collected


@pytest.fixture(scope="session")
def alertmanager_config() -> dict[str, Any]:
    return _load_yaml(MONITORING / "alertmanager" / "alertmanager.yml")


@pytest.fixture(scope="session")
def deploy_workflow() -> dict[str, Any]:
    return _load_yaml(REPO_ROOT / ".github" / "workflows" / "deploy.yml")


# ─── Registry ────────────────────────────────────────────────────────────────


class TestRegistry:
    def test_registry_exists_and_parses(self, registry: dict[str, Any]) -> None:
        assert registry, "infra/services.yml is empty"
        for key in ("org", "primary_region", "app_prefix", "units"):
            assert key in registry, f"registry is missing top-level key {key!r}"

    def test_every_unit_declares_required_fields(self, units: list[dict[str, Any]]) -> None:
        required = ("name", "path", "runtime", "port", "min_machines", "memory_mb", "description")
        for unit in units:
            for field in required:
                assert field in unit, f"{unit.get('name', '<unnamed>')}: missing {field!r}"

    def test_ports_are_unique(self, units: list[dict[str, Any]]) -> None:
        ports = [u["port"] for u in units]
        dupes = {p for p in ports if ports.count(p) > 1}
        assert not dupes, f"duplicate ports in registry: {sorted(dupes)}"

    def test_names_are_unique(self, units: list[dict[str, Any]]) -> None:
        names = _unit_ids(units)
        dupes = {n for n in names if names.count(n) > 1}
        assert not dupes, f"duplicate unit names: {sorted(dupes)}"

    def test_unit_paths_exist(self, units: list[dict[str, Any]]) -> None:
        for unit in units:
            assert (REPO_ROOT / unit["path"]).is_dir(), f"{unit['name']}: path {unit['path']} does not exist"

    def test_exactly_one_public_unit(self, units: list[dict[str, Any]]) -> None:
        # The whole security model assumes a single public entrypoint. If a
        # second unit ever goes public, that is an architecture decision that
        # must be made deliberately, not by editing a bool in a yaml file.
        public = [u["name"] for u in units if u.get("public")]
        assert public == ["api-gateway"], (
            f"expected api-gateway to be the only public unit, got {public}. "
            "Exposing another service bypasses the gateway's auth and rate limiting."
        )

    def test_critical_units_run_redundantly(self, units: list[dict[str, Any]]) -> None:
        # A single machine means a crash or a deploy is a full outage for that
        # unit. On the money path and the public edge that is not acceptable.
        for unit in units:
            if unit.get("critical") or unit.get("public"):
                assert unit["min_machines"] >= 2, (
                    f"{unit['name']} is critical/public but min_machines={unit['min_machines']}; "
                    "needs >=2 so a single machine failure isn't an outage"
                )

    def test_python_units_map_to_real_fastapi_services(self, units: list[dict[str, Any]]) -> None:
        for unit in units:
            if unit["runtime"] != "python":
                continue
            main_py = REPO_ROOT / unit["path"] / "app" / "main.py"
            assert main_py.is_file(), f"{unit['name']}: expected {main_py.relative_to(REPO_ROOT)}"
            text = main_py.read_text(encoding="utf-8")
            # The Dockerfile CMD is `uvicorn app.main:app`, so this must exist
            # or the container starts and immediately dies.
            assert re.search(r"^app\s*=\s*FastAPI", text, re.MULTILINE), (
                f"{unit['name']}: app/main.py has no module-level `app = FastAPI(...)`, "
                "but the generated Dockerfile CMD targets app.main:app"
            )

    def test_every_unit_serves_health(self, units: list[dict[str, Any]]) -> None:
        # Fly health checks, the Docker HEALTHCHECK, the deploy smoke test and
        # every Prometheus probe all depend on /health existing.
        for unit in units:
            if unit["runtime"] == "python":
                target = REPO_ROOT / unit["path"] / "app" / "main.py"
                needle = '"/health"'
            else:
                target = REPO_ROOT / unit["path"] / "src" / "routes" / "health.ts"
                needle = '"/health"'
            assert target.is_file(), f"{unit['name']}: {target.relative_to(REPO_ROOT)} missing"
            assert needle in target.read_text(encoding="utf-8"), (
                f"{unit['name']}: no /health route found in {target.relative_to(REPO_ROOT)}"
            )


# ─── Generated artifacts stay in sync ────────────────────────────────────────


class TestGeneratedArtifacts:
    def test_gen_infra_check_passes(self) -> None:
        """The committed artifacts must match what the registry generates.

        This is the anti-drift gate: without it, someone hand-edits a port in a
        fly.toml, the registry still says something else, and the gateway,
        Prometheus and the deploy matrix all disagree with reality.
        """
        result = subprocess.run(
            [sys.executable, "scripts/gen_infra.py", "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            "generated infra artifacts are out of date with infra/services.yml.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}\n"
            "Run `python scripts/gen_infra.py` and commit the result."
        )

    def test_every_unit_has_deployment_artifacts(self, units: list[dict[str, Any]]) -> None:
        for unit in units:
            base = REPO_ROOT / unit["path"]
            for artifact in ("Dockerfile", ".dockerignore", "fly.toml"):
                assert (base / artifact).is_file(), f"{unit['name']}: missing {artifact}"


# ─── Dockerfiles ─────────────────────────────────────────────────────────────


class TestDockerfiles:
    def test_runs_as_non_root(self, units: list[dict[str, Any]]) -> None:
        for unit in units:
            text = (REPO_ROOT / unit["path"] / "Dockerfile").read_text(encoding="utf-8")
            assert re.search(r"^USER\s+app\b", text, re.MULTILINE), (
                f"{unit['name']}: Dockerfile does not drop to a non-root USER. "
                "A container escape from a root process owns the host."
            )

    def test_base_images_are_pinned(self, units: list[dict[str, Any]]) -> None:
        for unit in units:
            text = (REPO_ROOT / unit["path"] / "Dockerfile").read_text(encoding="utf-8")
            for line in re.findall(r"^FROM\s+(\S+)", text, re.MULTILINE):
                assert ":" in line, f"{unit['name']}: unpinned base image {line!r} (no tag)"
                assert not line.endswith(":latest"), (
                    f"{unit['name']}: base image {line!r} uses :latest — builds become "
                    "irreproducible and can change under you between deploys"
                )

    def test_expose_and_healthcheck_match_registry_port(self, units: list[dict[str, Any]]) -> None:
        for unit in units:
            port = unit["port"]
            text = (REPO_ROOT / unit["path"] / "Dockerfile").read_text(encoding="utf-8")

            exposed = re.findall(r"^EXPOSE\s+(\d+)", text, re.MULTILINE)
            assert exposed == [str(port)], f"{unit['name']}: EXPOSE {exposed} != registry port {port}"

            assert "HEALTHCHECK" in text, f"{unit['name']}: Dockerfile has no HEALTHCHECK"
            # The probe honours an injected $PORT (Cloud Run assigns one) and
            # falls back to the registry port everywhere else.
            assert f"127.0.0.1:${{PORT:-{port}}}/health" in text, (
                f"{unit['name']}: HEALTHCHECK does not probe 127.0.0.1:$PORT (fallback {port})/health"
            )

    def test_python_units_start_uvicorn_on_the_right_port(self, units: list[dict[str, Any]]) -> None:
        for unit in units:
            if unit["runtime"] != "python":
                continue
            text = (REPO_ROOT / unit["path"] / "Dockerfile").read_text(encoding="utf-8")
            assert "app.main:app" in text, f"{unit['name']}: CMD does not target app.main:app"
            # Binding to 127.0.0.1 inside a container makes it unreachable from
            # outside it — a classic silent "deployed but nothing can reach it".
            assert "--host 0.0.0.0" in text, f"{unit['name']}: uvicorn must bind 0.0.0.0"
            # $PORT-aware with the registry port as the fallback, so the same
            # image runs on Cloud Run (injects PORT) and anywhere else.
            assert f"--port ${{PORT:-{unit['port']}}}" in text, (
                f"{unit['name']}: CMD port fallback != registry port {unit['port']}"
            )
            # `exec` so uvicorn becomes PID 1 and receives SIGTERM directly;
            # without it the shell swallows the signal and shutdown waits out
            # the full termination grace period instead of draining.
            assert 'CMD ["sh", "-c", "exec uvicorn' in text, (
                f"{unit['name']}: CMD must `exec` uvicorn so signals reach it as PID 1"
            )

    def test_dockerignore_excludes_secrets_and_venvs(self, units: list[dict[str, Any]]) -> None:
        for unit in units:
            text = (REPO_ROOT / unit["path"] / ".dockerignore").read_text(encoding="utf-8")
            assert ".env" in text, f"{unit['name']}: .dockerignore does not exclude .env — secrets could be baked into the image"
            if unit["runtime"] == "python":
                assert ".venv/" in text, f"{unit['name']}: .dockerignore should exclude .venv/"
            else:
                assert "node_modules/" in text, f"{unit['name']}: .dockerignore should exclude node_modules/"


# ─── Fly.io configs ──────────────────────────────────────────────────────────


class TestFlyConfigs:
    def test_fly_configs_parse(self, units: list[dict[str, Any]]) -> None:
        for unit in units:
            _load_toml(REPO_ROOT / unit["path"] / "fly.toml")

    def test_app_names_follow_the_prefix(self, registry: dict[str, Any], units: list[dict[str, Any]]) -> None:
        prefix = registry["app_prefix"]
        for unit in units:
            cfg = _load_toml(REPO_ROOT / unit["path"] / "fly.toml")
            assert cfg["app"] == f"{prefix}-{unit['name']}", (
                f"{unit['name']}: fly app name {cfg['app']!r} != {prefix}-{unit['name']!r}. "
                "The deploy workflow derives the app name from the registry, so a mismatch "
                "deploys into the wrong app or none at all."
            )

    def test_internal_port_matches_registry(self, units: list[dict[str, Any]]) -> None:
        for unit in units:
            cfg = _load_toml(REPO_ROOT / unit["path"] / "fly.toml")
            actual = cfg["http_service"]["internal_port"]
            assert actual == unit["port"], f"{unit['name']}: fly internal_port {actual} != registry {unit['port']}"

    def test_health_checks_are_configured(self, units: list[dict[str, Any]]) -> None:
        for unit in units:
            cfg = _load_toml(REPO_ROOT / unit["path"] / "fly.toml")
            checks = cfg["http_service"].get("checks")
            assert checks, f"{unit['name']}: no [[http_service.checks]] — Fly can't tell a wedged machine from a healthy one"
            assert any(c.get("path") == "/health" for c in checks), f"{unit['name']}: no check against /health"

    def test_min_machines_matches_registry(self, units: list[dict[str, Any]]) -> None:
        for unit in units:
            cfg = _load_toml(REPO_ROOT / unit["path"] / "fly.toml")
            actual = cfg["http_service"]["min_machines_running"]
            assert actual == unit["min_machines"], (
                f"{unit['name']}: fly min_machines_running {actual} != registry {unit['min_machines']}"
            )

    def test_critical_units_never_auto_stop(self, units: list[dict[str, Any]]) -> None:
        # A cold-starting payment webhook handler drops provider callbacks that
        # are not always retried; a cold-starting edge adds latency to every
        # first request.
        for unit in units:
            if not (unit.get("critical") or unit.get("public")):
                continue
            cfg = _load_toml(REPO_ROOT / unit["path"] / "fly.toml")
            assert cfg["http_service"]["auto_stop_machines"] is False, (
                f"{unit['name']} is critical/public but has auto_stop_machines enabled"
            )

    def test_only_public_unit_forces_https(self, units: list[dict[str, Any]]) -> None:
        # Internal units are reached over Fly's private network on http; forcing
        # HTTPS on them breaks gateway->service calls.
        for unit in units:
            cfg = _load_toml(REPO_ROOT / unit["path"] / "fly.toml")
            forced = cfg["http_service"]["force_https"]
            assert forced is bool(unit.get("public", False)), (
                f"{unit['name']}: force_https={forced} but public={bool(unit.get('public'))}"
            )


# ─── Cross-check against the gateway's own config ────────────────────────────


class TestGatewayPortAlignment:
    """The registry and the gateway must agree on where every service lives.

    This is the single highest-value test in the file: if these drift, the
    gateway proxies to a port nothing is listening on and every request through
    it 502s, while all the individual services look perfectly healthy.
    """

    def test_gateway_service_urls_match_registry_ports(self, units: list[dict[str, Any]]) -> None:
        source = GATEWAY_CONFIG_TS.read_text(encoding="utf-8")

        declared: dict[str, int] = {}
        for env_name, port in re.findall(
            r"(\w+_SERVICE_URL):\s*z\.string\(\)\.url\(\)\.default\(\"http://localhost:(\d+)\"\)",
            source,
        ):
            declared[env_name] = int(port)

        assert declared, f"could not parse any *_SERVICE_URL defaults out of {GATEWAY_CONFIG_TS.name}"

        for unit in units:
            env_name = unit.get("gateway_env")
            if not env_name:
                continue  # the gateway itself
            assert env_name in declared, (
                f"{unit['name']}: registry declares gateway_env={env_name} but the gateway's "
                f"config.ts has no such default"
            )
            assert declared[env_name] == unit["port"], (
                f"PORT DRIFT: {unit['name']} is on {unit['port']} per infra/services.yml, but the "
                f"gateway's {env_name} defaults to port {declared[env_name]}. "
                "The gateway would proxy into the void."
            )

    def test_gateway_port_matches_registry(self, units: list[dict[str, Any]]) -> None:
        gateway = next(u for u in units if u["name"] == "api-gateway")
        source = GATEWAY_CONFIG_TS.read_text(encoding="utf-8")
        match = re.search(r"PORT:\s*z\.coerce\.number\(\)[^\n]*?\.default\((\d+)\)", source)
        assert match, "could not find the PORT default in the gateway config"
        assert int(match.group(1)) == gateway["port"], (
            f"gateway listens on {match.group(1)} but the registry says {gateway['port']}"
        )


# ─── Monitoring stack ────────────────────────────────────────────────────────


class TestMonitoringConfigs:
    def test_all_monitoring_configs_parse(self) -> None:
        for path in sorted(MONITORING.rglob("*.yml")):
            try:
                _load_yaml(path)
            except yaml.YAMLError as exc:
                pytest.fail(f"{path.relative_to(REPO_ROOT)} is not valid YAML: {exc}")
        for path in sorted(MONITORING.rglob("*.json")):
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                pytest.fail(f"{path.relative_to(REPO_ROOT)} is not valid JSON: {exc}")

    def test_compose_mounts_exist(self) -> None:
        """Every config file the compose stack bind-mounts must actually exist.

        A missing mount source silently becomes an empty directory in Docker,
        so the container starts with default config and the stack looks fine
        while monitoring nothing.
        """
        compose = _load_yaml(MONITORING / "docker-compose.monitoring.yml")
        for svc_name, svc in compose["services"].items():
            for volume in svc.get("volumes", []):
                source = volume.split(":")[0]
                if not source.startswith("./"):
                    continue  # named volume or absolute host path
                resolved = (MONITORING / source[2:]).resolve()
                assert resolved.exists(), (
                    f"compose service {svc_name!r} mounts {source} which does not exist"
                )

    def test_compose_images_are_pinned(self) -> None:
        compose = _load_yaml(MONITORING / "docker-compose.monitoring.yml")
        for svc_name, svc in compose["services"].items():
            image = svc["image"]
            assert ":" in image, f"{svc_name}: unpinned image {image!r}"
            assert not image.endswith(":latest"), (
                f"{svc_name}: image {image!r} uses :latest — the monitoring plane must not "
                "change behaviour underneath an incident"
            )

    def test_prometheus_references_existing_rule_and_target_files(self) -> None:
        prom = _load_yaml(MONITORING / "prometheus" / "prometheus.yml")

        assert prom.get("rule_files"), "prometheus.yml declares no rule_files — no alerts would load"
        rules_dir = MONITORING / "prometheus" / "rules"
        assert list(rules_dir.glob("*.yml")), f"no rule files in {rules_dir.relative_to(REPO_ROOT)}"

        # Every file_sd target list referenced must exist on disk under the
        # path the compose file mounts it to.
        for job in prom["scrape_configs"]:
            for sd in job.get("file_sd_configs", []):
                for ref in sd["files"]:
                    local = MONITORING / "prometheus" / ref.split("/etc/prometheus/")[-1]
                    assert local.is_file(), (
                        f"job {job['job_name']!r} references {ref}, which maps to a missing file "
                        f"({local.relative_to(REPO_ROOT)})"
                    )

    def test_prometheus_alerting_points_at_alertmanager(self) -> None:
        prom = _load_yaml(MONITORING / "prometheus" / "prometheus.yml")
        targets = [
            t
            for am in prom["alerting"]["alertmanagers"]
            for sc in am["static_configs"]
            for t in sc["targets"]
        ]
        assert any("alertmanager" in t for t in targets), (
            "Prometheus has no alertmanager target — alerts would fire into nothing"
        )

    def test_every_unit_is_probed(self, registry: dict[str, Any], units: list[dict[str, Any]]) -> None:
        """No deployable unit may be invisible to monitoring."""
        targets_dir = MONITORING / "prometheus" / "targets"
        for env_file in ("services-local.json", "services-fly.json"):
            entries = json.loads((targets_dir / env_file).read_text(encoding="utf-8"))
            probed = {e["labels"]["service"] for e in entries if e["targets"]}
            missing = set(_unit_ids(units)) - probed
            assert not missing, f"{env_file}: these units have no health probe: {sorted(missing)}"

    def test_probe_targets_use_registry_ports(self, units: list[dict[str, Any]]) -> None:
        entries = json.loads(
            (MONITORING / "prometheus" / "targets" / "services-local.json").read_text(encoding="utf-8")
        )
        by_name = {e["labels"]["service"]: e for e in entries if e["targets"]}
        for unit in units:
            target = by_name[unit["name"]]["targets"][0]
            assert target.endswith(f":{unit['port']}/health"), (
                f"{unit['name']}: probe target {target} does not use registry port {unit['port']}"
            )

    def test_every_unit_has_an_app_metrics_target(self, units: list[dict[str, Any]]) -> None:
        """No deployable unit may be invisible to the T309b /metrics scrape."""
        targets_dir = MONITORING / "prometheus" / "targets"
        for env_file in ("app-metrics-local.json", "app-metrics-fly.json"):
            entries = json.loads((targets_dir / env_file).read_text(encoding="utf-8"))
            scraped = {e["labels"]["service"] for e in entries if e["targets"]}
            missing = set(_unit_ids(units)) - scraped
            assert not missing, f"{env_file}: these units have no /metrics scrape target: {sorted(missing)}"

    def test_app_metrics_targets_use_registry_ports_with_no_path(self, units: list[dict[str, Any]]) -> None:
        entries = json.loads(
            (MONITORING / "prometheus" / "targets" / "app-metrics-local.json").read_text(encoding="utf-8")
        )
        by_name = {e["labels"]["service"]: e for e in entries if e["targets"]}
        for unit in units:
            target = by_name[unit["name"]]["targets"][0]
            # Bare host:port — the job's own `metrics_path: /metrics` supplies
            # the path, so a target that already bakes one in would produce a
            # wrong scrape URL (double path) rather than simply failing loud.
            assert target.endswith(f":{unit['port']}"), (
                f"{unit['name']}: app-metrics target {target} does not end in registry port {unit['port']}"
            )
            assert "/" not in target, f"{unit['name']}: app-metrics target {target} should not include a path"

    def test_app_metrics_job_scrapes_the_metrics_path(self) -> None:
        prom = _load_yaml(MONITORING / "prometheus" / "prometheus.yml")
        job = next(j for j in prom["scrape_configs"] if j["job_name"] == "app-metrics")
        assert job["metrics_path"] == "/metrics"

    def test_critical_units_are_labelled_critical(self, units: list[dict[str, Any]]) -> None:
        # The page-vs-ticket alert routing keys off this label. If it's wrong,
        # a payment outage files a ticket instead of waking someone.
        entries = json.loads(
            (MONITORING / "prometheus" / "targets" / "services-fly.json").read_text(encoding="utf-8")
        )
        by_name = {e["labels"]["service"]: e["labels"] for e in entries if e["targets"]}
        for unit in units:
            expected = "critical" if (unit.get("critical") or unit.get("public")) else "standard"
            actual = by_name[unit["name"]]["criticality"]
            assert actual == expected, f"{unit['name']}: criticality label {actual!r}, expected {expected!r}"


# ─── Alert rules ─────────────────────────────────────────────────────────────


class TestAlertRules:
    def test_alerts_exist(self, alert_rules: list[dict[str, Any]]) -> None:
        assert alert_rules, "no alert rules defined — the monitoring stack would never notify anyone"

    def test_every_alert_has_a_known_severity(self, alert_rules: list[dict[str, Any]]) -> None:
        # Alertmanager routes exclusively on severity; an alert with an
        # unrecognised value silently falls through to the default receiver.
        allowed = {"page", "ticket"}
        for rule in alert_rules:
            severity = rule.get("labels", {}).get("severity")
            assert severity in allowed, (
                f"alert {rule['alert']}: severity={severity!r} is not one of {sorted(allowed)}"
            )

    def test_every_alert_is_actionable(self, alert_rules: list[dict[str, Any]]) -> None:
        # An alert without a summary and a runbook is a 3am puzzle, not a signal.
        for rule in alert_rules:
            annotations = rule.get("annotations", {})
            assert annotations.get("summary"), f"alert {rule['alert']}: missing annotations.summary"
            assert annotations.get("runbook"), f"alert {rule['alert']}: missing annotations.runbook"

    def test_every_alert_waits_before_firing(self, alert_rules: list[dict[str, Any]]) -> None:
        # Without `for:`, a single failed scrape pages someone. That trains
        # people to ignore the pager, which is worse than no pager.
        for rule in alert_rules:
            assert rule.get("for"), f"alert {rule['alert']}: no `for:` duration — would fire on a single blip"

    def test_runbook_links_resolve(self, alert_rules: list[dict[str, Any]]) -> None:
        """Every runbook anchor an alert points at must exist in the runbook."""
        for rule in alert_rules:
            ref = rule["annotations"]["runbook"]
            doc_path, _, anchor = ref.partition("#")
            target = REPO_ROOT / doc_path
            assert target.is_file(), f"alert {rule['alert']}: runbook {doc_path} does not exist"
            if anchor:
                headings = re.findall(r"^#{1,6}\s+(.+)$", target.read_text(encoding="utf-8"), re.MULTILINE)
                slugs = {re.sub(r"[^a-z0-9]+", "", h.lower()) for h in headings}
                assert re.sub(r"[^a-z0-9]+", "", anchor.lower()) in slugs, (
                    f"alert {rule['alert']}: runbook anchor #{anchor} not found in {doc_path}"
                )


# ─── Alertmanager ────────────────────────────────────────────────────────────


class TestAlertmanager:
    def test_all_routed_receivers_are_defined(self, alertmanager_config: dict[str, Any]) -> None:
        # A route to an undefined receiver is a config error that Alertmanager
        # rejects at startup — catching it here beats catching it during an
        # incident when the stack won't come up.
        defined = {r["name"] for r in alertmanager_config["receivers"]}
        route = alertmanager_config["route"]
        referenced = {route["receiver"]}
        referenced.update(sub["receiver"] for sub in route.get("routes", []))
        missing = referenced - defined
        assert not missing, f"routes reference undefined receivers: {sorted(missing)}"

    def test_page_severity_reaches_a_pager(self, alertmanager_config: dict[str, Any]) -> None:
        by_name = {r["name"]: r for r in alertmanager_config["receivers"]}
        page_routes = [
            sub
            for sub in alertmanager_config["route"].get("routes", [])
            if any('severity = "page"' in str(m) for m in sub.get("matchers", []))
        ]
        assert page_routes, "no route matches severity=page — critical alerts would never page"
        assert any("pagerduty_configs" in by_name[sub["receiver"]] for sub in page_routes), (
            "severity=page routes to no PagerDuty receiver; a critical alert would only post to chat"
        )

    def test_secrets_come_from_env_not_literals(self, alertmanager_config: dict[str, Any]) -> None:
        raw = (MONITORING / "alertmanager" / "alertmanager.yml").read_text(encoding="utf-8")
        for receiver in alertmanager_config["receivers"]:
            for kind in ("pagerduty_configs", "slack_configs"):
                for entry in receiver.get(kind, []):
                    secret = entry.get("routing_key") or entry.get("api_url") or ""
                    assert secret.startswith("${"), (
                        f"receiver {receiver['name']}: {kind} credential is not an env reference "
                        f"({secret[:24]!r}...). Credentials must never be committed."
                    )
        assert "hooks.slack.com/services/T" not in raw, "a real Slack webhook URL appears to be committed"


# ─── Grafana ─────────────────────────────────────────────────────────────────


class TestGrafana:
    def test_dashboards_are_valid_json_with_a_uid(self) -> None:
        dashboards = list((MONITORING / "grafana" / "dashboards").glob("*.json"))
        assert dashboards, "no Grafana dashboards provisioned"
        for path in dashboards:
            doc = json.loads(path.read_text(encoding="utf-8"))
            assert doc.get("uid"), f"{path.name}: dashboard has no uid (provisioning needs a stable one)"
            assert doc.get("title"), f"{path.name}: dashboard has no title"
            assert doc.get("panels"), f"{path.name}: dashboard has no panels"

    def test_dashboard_datasources_are_provisioned(self) -> None:
        """Panels must reference datasource UIDs that provisioning actually creates."""
        datasources = _load_yaml(MONITORING / "grafana" / "provisioning" / "datasources" / "datasources.yml")
        known = {ds["uid"] for ds in datasources["datasources"]}

        for path in (MONITORING / "grafana" / "dashboards").glob("*.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            for panel in doc["panels"]:
                uid = (panel.get("datasource") or {}).get("uid")
                if uid:
                    assert uid in known, (
                        f"{path.name}: panel {panel.get('title')!r} references datasource uid "
                        f"{uid!r}, which provisioning does not create (known: {sorted(known)})"
                    )

    def test_dashboard_provider_path_matches_compose_mount(self) -> None:
        provider = _load_yaml(MONITORING / "grafana" / "provisioning" / "dashboards" / "dashboards.yml")
        declared = provider["providers"][0]["options"]["path"]

        compose = _load_yaml(MONITORING / "docker-compose.monitoring.yml")
        mounts = compose["services"]["grafana"]["volumes"]
        container_paths = {m.split(":")[1] for m in mounts if m.startswith("./")}

        assert declared in container_paths, (
            f"dashboard provider reads {declared}, but compose mounts {sorted(container_paths)} — "
            "dashboards would never load"
        )


# ─── Deploy workflow ─────────────────────────────────────────────────────────


class TestDeployWorkflow:
    def test_workflow_parses(self, deploy_workflow: dict[str, Any]) -> None:
        assert deploy_workflow["jobs"], "deploy workflow defines no jobs"

    def test_deploy_is_gated_on_ci_success(self, deploy_workflow: dict[str, Any]) -> None:
        # PyYAML parses a bare `on:` key as the boolean True, not the string.
        triggers = deploy_workflow.get("on") or deploy_workflow.get(True)
        assert "workflow_run" in triggers, "deploy does not trigger off the CI workflow"
        assert triggers["workflow_run"]["workflows"] == ["CI"]

        guard = deploy_workflow["jobs"]["guard"]
        assert "conclusion == 'success'" in guard["if"], (
            "the guard job does not require the upstream CI run to have succeeded — "
            "a red build could deploy"
        )

    def test_guard_verifies_artifacts_are_in_sync(self, deploy_workflow: dict[str, Any]) -> None:
        steps = deploy_workflow["jobs"]["guard"]["steps"]
        assert any("gen_infra.py --check" in str(s.get("run", "")) for s in steps), (
            "the guard job does not run gen_infra --check, so a hand-edited Dockerfile "
            "could deploy out of sync with the registry"
        )

    def test_production_deploys_require_approval(self, deploy_workflow: dict[str, Any]) -> None:
        for job_name in ("deploy-services", "deploy-gateway"):
            assert deploy_workflow["jobs"][job_name].get("environment") == "production", (
                f"{job_name} does not use the `production` environment, so it would deploy "
                "without the manual approval gate"
            )

    def test_gateway_deploys_after_services(self, deploy_workflow: dict[str, Any]) -> None:
        needs = deploy_workflow["jobs"]["deploy-gateway"]["needs"]
        assert "deploy-services" in needs, (
            "the public edge must roll after the services behind it, or it will briefly "
            "route to stale/absent backends"
        )

    def test_every_deploy_is_smoke_tested(self, deploy_workflow: dict[str, Any]) -> None:
        for job_name in ("deploy-services", "deploy-gateway"):
            steps = deploy_workflow["jobs"][job_name]["steps"]
            assert any("/health" in str(s.get("run", "")) for s in steps), (
                f"{job_name} has no post-deploy /health smoke test"
            )

    def test_service_deploys_do_not_fail_fast(self, deploy_workflow: dict[str, Any]) -> None:
        strategy = deploy_workflow["jobs"]["deploy-services"]["strategy"]
        assert strategy.get("fail-fast") is False, (
            "fail-fast would cancel in-flight deploys, leaving the platform in a "
            "half-rolled state that's harder to diagnose"
        )

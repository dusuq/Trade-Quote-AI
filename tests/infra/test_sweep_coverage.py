"""Guards on what the test/lint sweep actually covers (T313).

Every finding this file pins was a *silent* one: a gate that printed a green
summary while never running against some of the code it claimed to cover.
That failure mode has now recurred three times in this repo —

  - T205: notification-service was missing from SERVICE_DIRS entirely, so the
    sweep said "all services green" while never running its suite at all.
  - T30x batch audit: integration-service, same gap, found the same way.
  - T313: the sweep ran `ruff check app`, so no service's tests/ directory had
    ever been linted — and CI, which ran `ruff check .`, was already red on
    analytics-service while the local sweep reported success.

— which is why it is now asserted rather than left to review. A weaker local
gate than the remote one is worse than no local gate: it manufactures
confidence instead of merely failing to provide it.

These tests read the sweep and CI *as data*. They deliberately do not execute
either one (that is what running the sweep is for) — they check that the two
still agree about scope, which is the property that kept silently breaking.

Run:  python -m pytest tests/infra/test_sweep_coverage.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SWEEP = REPO_ROOT / "scripts" / "run_all_tests.py"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SERVICES_DIR = REPO_ROOT / "services"
ROOT_RUFF_CONFIG = REPO_ROOT / "ruff.toml"


@pytest.fixture(scope="module")
def sweep_source() -> str:
    return SWEEP.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ci_python_lane() -> str:
    """The Python job's steps, flattened to one searchable string."""
    doc = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return "\n".join(str(step.get("run", "")) for step in doc["jobs"]["python"]["steps"])


def _services_on_disk() -> set[str]:
    return {p.name for p in SERVICES_DIR.iterdir() if p.is_dir() and (p / "pyproject.toml").is_file()}


def _services_in_sweep(source: str) -> set[str]:
    # SERVICE_DIRS entries look like: ROOT_DIR / "services" / "auth-service"
    block = source.split("SERVICE_DIRS", 1)[1].split("]", 1)[0]
    return set(re.findall(r'"services"\s*/\s*"([^"]+)"', block))


class TestEveryServiceIsInTheSweep:
    def test_no_service_is_missing_from_the_sweep(self, sweep_source: str) -> None:
        """A service absent here is a service nothing ever tests (T205, T30x)."""
        missing = _services_on_disk() - _services_in_sweep(sweep_source)
        assert not missing, (
            f"these services exist on disk but are not in SERVICE_DIRS, so the sweep "
            f"never runs them and still reports success: {sorted(missing)}"
        )

    def test_the_sweep_lists_no_service_that_does_not_exist(self, sweep_source: str) -> None:
        # The inverse: a stale entry is skipped with a one-line notice that is
        # easy to miss in a long log, so the sweep goes green having run less.
        stale = _services_in_sweep(sweep_source) - _services_on_disk()
        assert not stale, f"SERVICE_DIRS references non-existent services: {sorted(stale)}"


class TestTestCodeIsLinted:
    def test_sweep_does_not_lint_only_the_app_directory(self, sweep_source: str) -> None:
        """The exact T313 regression: `ruff check app` skips every test file."""
        assert '[ruff_cmd, "check", "app"]' not in sweep_source, (
            "the sweep lints only app/ again — no service's tests/ would be checked. "
            'Use `[ruff_cmd, "check", "."]` so test code is covered.'
        )

    def test_sweep_lints_the_whole_service_directory(self, sweep_source: str) -> None:
        assert '[ruff_cmd, "check", "."]' in sweep_source, (
            "the sweep's ruff invocation no longer targets the whole service directory"
        )

    def test_repo_root_tests_and_scripts_are_linted(self, sweep_source: str) -> None:
        # tests/ and scripts/ have no service pyproject.toml above them, so they
        # are only linted if something asks for them by name.
        assert '"check", "tests", "scripts"' in sweep_source, (
            "the sweep no longer lints repo-root tests/ and scripts/ — including "
            "tests/infra and tests/security, which CI actually executes"
        )

    def test_repo_root_ruff_config_exists_and_names_its_rules(self) -> None:
        """Without an explicit select, this lane silently inherits ruff's defaults.

        Those defaults change between releases, and this repo pins only
        `ruff>=0.8`, so results would vary by machine and by install date.
        """
        assert ROOT_RUFF_CONFIG.is_file(), "repo-root ruff.toml is missing"
        config = ROOT_RUFF_CONFIG.read_text(encoding="utf-8")
        assert "select" in config, (
            "ruff.toml does not name its rules, so repo-root lint strictness is "
            "whatever the installed ruff defaults to that week"
        )


class TestSweepAndCIAgree:
    """The sweep must not be weaker than CI, or it hides what CI will reject."""

    def test_ci_lints_the_whole_service_directory(self, ci_python_lane: str) -> None:
        assert "ruff check ." in ci_python_lane, (
            "CI's Python lane no longer runs `ruff check .` per service"
        )

    def test_ci_lints_repo_root_tests_and_scripts(self, ci_python_lane: str) -> None:
        assert "ruff check tests scripts" in ci_python_lane, (
            "CI no longer lints repo-root tests/ and scripts/, so that code is "
            "unguarded on the only gate that blocks a merge"
        )

    def test_sweep_and_ci_run_the_same_per_service_commands(
        self, sweep_source: str, ci_python_lane: str
    ) -> None:
        # Pinned as a pair: T313 existed because these two drifted apart and
        # nothing noticed until CI failed on code the local sweep called clean.
        # The sweep builds argv lists while CI writes a shell line, so the same
        # command is spelled differently in each — hence the explicit mapping
        # rather than a substring search for one form in both.
        equivalents = {
            "ruff check .": '[ruff_cmd, "check", "."]',
            "mypy .": '[mypy_cmd, "."]',
        }
        for ci_form, sweep_form in equivalents.items():
            assert sweep_form in sweep_source, (
                f"the sweep no longer runs the equivalent of `{ci_form}` "
                f"(expected {sweep_form} in scripts/run_all_tests.py)"
            )
            assert ci_form in ci_python_lane, f"CI no longer runs `{ci_form}`"

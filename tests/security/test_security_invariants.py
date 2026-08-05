"""Security regression suite (T310 / M27).

Every test here pins an invariant that was either found broken during the T310
review, or is load-bearing enough that silently losing it would be a breach.
They are static/structural checks by design: they run with no database, no
network, and no running services, so they execute on every CI run rather than
being skipped like tests/integration/test_postgres_rls.py (which `skipif`s
itself whenever Postgres is unreachable — that is exactly how the RLS
owner-bypass finding survived unnoticed).

What this suite CANNOT prove is called out in
docs/13-SECURITY-REVIEW-OWASP.md: RLS behaviour against a live database, real
TLS/header behaviour, and anything requiring a deployed environment.

Run:  python -m pytest tests/security -q
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SERVICES = REPO_ROOT / "services"
GATEWAY_SRC = REPO_ROOT / "apps" / "api-gateway" / "src"
MIGRATIONS = REPO_ROOT / "infra" / "db" / "migrations"

# The committed dev-only secrets. Their existence is fine; shipping them to a
# non-local environment is not, which is what the startup guards prevent.
DEV_JWT_SECRET = "local-dev-only-change-me-32byte-minimum-secret"
DEV_FERNET_KEY = "wz1hLmNyzDikO1PBHvcHOl_5vsNaKlfQoR3MTexIu4o="


def _py_sources(service: str) -> list[Path]:
    app = SERVICES / service / "app"
    return [p for p in app.rglob("*.py") if "__pycache__" not in p.parts]


def _all_service_names() -> list[str]:
    return sorted(p.name for p in SERVICES.iterdir() if (p / "app").is_dir())



def _strip_ts_comments(src: str) -> str:
    """Remove // line comments and /* */ blocks.

    Mutation testing showed the earlier text-matching assertions passed while
    the protection was commented out — the assertion matched the text inside
    the comment. Anything asserting "this code exists" must look at code only.
    """
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    return "\n".join(line for line in src.splitlines() if not line.strip().startswith("//"))


def _strip_py_comments(src: str) -> str:
    return "\n".join(line for line in src.splitlines() if not line.strip().startswith("#"))


def _strip_sql_comments(src: str) -> str:
    return "\n".join(line for line in src.splitlines() if not line.strip().startswith("--"))


def _auth_routes_src() -> str:
    """auth-service's routes.py with comments stripped (see _strip_ts_comments)."""
    return _strip_py_comments(
        (SERVICES / "auth-service" / "app" / "interface" / "routes.py").read_text(encoding="utf-8")
    )


@pytest.fixture(scope="session")
def proxy_src() -> str:
    return _strip_ts_comments((GATEWAY_SRC / "plugins" / "proxy.ts").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def auth_src() -> str:
    return _strip_ts_comments((GATEWAY_SRC / "plugins" / "auth.ts").read_text(encoding="utf-8"))


# ─── A01: Broken access control — the gateway trust boundary ─────────────────


class TestGatewayTrustBoundary:
    """Downstream services trust `x-tenant-id` blindly (by convention, and
    enforced by scripts/check_conventions.py which forbids them decoding JWTs).

    That makes the gateway's header handling the single control standing
    between a public request and cross-tenant access. If a client-supplied
    `x-tenant-id` ever survives to an upstream, any authenticated user — or on
    a public route, any anonymous caller — reads and writes another tenant's
    data. These tests make that regression impossible to merge.
    """

    def test_identity_headers_are_stripped_from_client_requests(self, proxy_src: str) -> None:
        for header in ("x-tenant-id", "x-user-id", "x-user-roles"):
            assert re.search(rf'delete\s+headers\[["\']{header}["\']\]', proxy_src), (
                f"proxy.ts no longer deletes a client-supplied {header!r} header. "
                "On a public route (request.auth undefined) this forwards an "
                "attacker-chosen tenant id to an upstream that trusts it implicitly."
            )

    def test_identity_headers_are_stripped_before_being_repopulated(self, proxy_src: str) -> None:
        # Order matters: a delete placed *after* the auth block would wipe the
        # verified values instead of the attacker's.
        delete_at = proxy_src.index('delete headers["x-tenant-id"]')
        assign_at = proxy_src.index('headers["x-tenant-id"] = request.auth')
        assert delete_at < assign_at, (
            "the x-tenant-id delete must come BEFORE the authenticated assignment; "
            "reversed, it strips the trusted value and forwards nothing"
        )

    def test_forwarded_for_is_overwritten_not_appended(self, proxy_src: str) -> None:
        # esign-service writes this into a legal audit trail as the signer's IP.
        assert re.search(r'headers\["x-forwarded-for"\]\s*=\s*request\.ip', proxy_src), (
            "x-forwarded-for must be OVERWRITTEN with the real peer address. If a "
            "caller can choose it, they choose what gets recorded as the signer's "
            "IP in the e-signature audit trail."
        )
        # Assignment, never append: `+=` or concatenating the inbound value
        # would let a caller prepend a spoofed address that downstream parsers
        # then read as the client IP. Comments are stripped first so prose
        # about the header doesn't count as a reference.
        code_only = "\n".join(
            line for line in proxy_src.splitlines() if not line.strip().startswith("//")
        )
        references = [ln.strip() for ln in code_only.splitlines() if "x-forwarded-for" in ln]
        assert references == ['headers["x-forwarded-for"] = request.ip;'], (
            f"x-forwarded-for should be touched exactly once, by direct assignment. Found: "
            f"{references}"
        )

    def test_identity_headers_only_set_from_verified_claims(self, proxy_src: str) -> None:
        for header, claim in (
            ("x-tenant-id", "request.auth.tid"),
            ("x-user-id", "request.auth.sub"),
        ):
            assert f'headers["{header}"] = {claim}' in proxy_src, (
                f"{header} must be derived from verified JWT claims ({claim}), never "
                "from request input"
            )


class TestPublicRouteAllowlist:
    """A public route is a route with no tenant check at all. The allowlist
    must stay narrow and anchored — a loose pattern is an authorization
    bypass, not a cosmetic issue."""

    def test_public_patterns_are_anchored(self, auth_src: str) -> None:
        block = auth_src.split("PUBLIC_PATH_PATTERNS")[1].split("];")[0]
        patterns = re.findall(r"^\s*(/\^.*\$/),?\s*$", block, re.MULTILINE)
        assert patterns, "could not parse PUBLIC_PATH_PATTERNS — check the test, then the file"
        for pattern in patterns:
            assert pattern.startswith("/^") and pattern.endswith("$/"), (
                f"public route pattern {pattern} is not anchored at both ends. An "
                "unanchored pattern matches far more than intended and can expose "
                "the authenticated surface behind the same prefix."
            )

    def test_no_wildcard_public_prefixes(self, auth_src: str) -> None:
        block = auth_src.split("PUBLIC_PATH_PATTERNS")[1].split("];")[0]
        # `.*` inside a public route pattern would swallow sibling authenticated
        # paths, e.g. /v1/sign/.* also matching /v1/signature-requests/....
        assert ".*" not in block, (
            "a public route pattern contains `.*`, which is broad enough to expose "
            "authenticated routes sharing the prefix"
        )

    def test_known_public_paths_are_exactly_the_expected_set(self, auth_src: str) -> None:
        # Locks the blast radius: adding a public path should be a deliberate,
        # reviewed change that updates this list too.
        exact = set(re.findall(r'"(/[^"]*)"', auth_src.split("PUBLIC_PATHS")[1].split("]")[0]))
        assert exact == {"/health", "/metrics", "/v1/auth/register", "/v1/auth/login"}, (
            f"the set of unauthenticated exact paths changed: {sorted(exact)}. "
            "Every entry here is reachable with no token at all."
        )


# ─── A02/A07: Secrets must fail closed ───────────────────────────────────────


class TestFailClosedSecrets:
    """The T310 headline finding: the gateway and auth-service both defaulted
    to the SAME committed JWT secret, with no production guard anywhere in the
    codebase. Anyone reading this public repo could forge a token for any
    tenant with any role. It failed OPEN — silently indistinguishable from a
    correct deployment."""

    def test_gateway_refuses_dev_jwt_secret_in_production(self) -> None:
        src = _strip_ts_comments((GATEWAY_SRC / "config.ts").read_text(encoding="utf-8"))
        #  so a renamed/disabled `DISABLED_assertProductionSecrets` does not
        # satisfy a naive substring check (a real mutation that slipped through).
        assert re.search(r"assertProductionSecrets\s*\(cfg\)", src), (
            "loadConfig no longer CALLS assertProductionSecrets — the guard may still be "
            "defined but never runs"
        )
        assert re.search(r"export function assertProductionSecrets", src), (
            "gateway lost its production secret guard"
        )
        assert "DEV_ONLY_JWT_SECRET" in src
        assert re.search(r"throw new Error", src), (
            "the guard must THROW, not warn. A warning in a log nobody reads is how "
            "a fail-open config reaches production."
        )

    def test_auth_service_refuses_dev_jwt_secret_in_production(self) -> None:
        src = _strip_py_comments(
            (SERVICES / "auth-service" / "app" / "config.py").read_text(encoding="utf-8")
        )
        assert re.search(r"^\s*_assert_production_secrets\(self\)", src, re.MULTILINE), (
            "auth-service's Settings no longer calls _assert_production_secrets"
        )
        assert "InsecureConfigurationError" in src
        assert "model_post_init" in src, (
            "the guard must run automatically on Settings construction, not only when "
            "something remembers to call it"
        )

    def test_integration_service_refuses_dev_encryption_key_in_production(self) -> None:
        src = _strip_py_comments(
            (SERVICES / "integration-service" / "app" / "config.py").read_text(encoding="utf-8")
        )
        assert re.search(r"^\s*_assert_production_secrets\(self\)", src, re.MULTILINE), (
            "integration-service lost its guard — the committed Fernet key protects "
            "third-party OAuth tokens at rest"
        )
        assert "DEV_ONLY_TOKEN_ENCRYPTION_KEY" in src

    @pytest.mark.parametrize(
        "path,marker",
        [
            ("apps/api-gateway/src/config.ts", "production"),
            ("services/auth-service/app/config.py", "production"),
            ("services/integration-service/app/config.py", "production"),
        ],
    )
    def test_guards_cover_staging_too(self, path: str, marker: str) -> None:
        src = (REPO_ROOT / path).read_text(encoding="utf-8")
        assert "staging" in src, (
            f"{path}: the non-local env list must include staging. Staging holds real "
            "customer-shaped data often enough that dev secrets there are a real risk."
        )
        assert marker in src


class TestPasswordAndTokenHandling:
    def test_password_hashing_meets_owasp_iteration_floor(self) -> None:
        src = (SERVICES / "auth-service" / "app" / "config.py").read_text(encoding="utf-8")
        match = re.search(r"pbkdf2_iterations:\s*int\s*=\s*([\d_]+)", src)
        assert match, "could not find pbkdf2_iterations"
        iterations = int(match.group(1).replace("_", ""))
        # OWASP Password Storage Cheat Sheet: 600,000 for PBKDF2-HMAC-SHA256.
        assert iterations >= 600_000, (
            f"PBKDF2 iterations dropped to {iterations:,}; OWASP's floor for "
            "PBKDF2-HMAC-SHA256 is 600,000. Lowering this makes every stored hash "
            "cheaper to crack offline."
        )

    def test_password_comparison_is_constant_time(self) -> None:
        src = (SERVICES / "auth-service" / "app" / "application" / "security.py").read_text(
            encoding="utf-8"
        )
        assert "hmac.compare_digest" in src, (
            "password verification must use hmac.compare_digest; `==` on a digest leaks "
            "match length through timing"
        )

    def test_refresh_tokens_are_stored_hashed(self) -> None:
        src = (SERVICES / "auth-service" / "app" / "application" / "security.py").read_text(
            encoding="utf-8"
        )
        assert "hashlib.sha256" in src and "hash_token" in src, (
            "refresh tokens must be stored as hashes so a database read cannot be "
            "replayed as a live session"
        )
        assert "secrets.token_urlsafe" in src, "refresh tokens must come from a CSPRNG"

    def test_jwt_algorithm_is_pinned_on_verification(self) -> None:
        src = (GATEWAY_SRC / "auth.ts").read_text(encoding="utf-8")
        assert 'algorithms: ["HS256"]' in src, (
            "JWT verification must pin the algorithm. Without it, a token with "
            '`alg: "none"` (or an RS256/HS256 confusion) can bypass verification.'
        )


# ─── A03: Injection ──────────────────────────────────────────────────────────


class TestNoSqlInjection:
    """Both patterns are deliberately LINE-SCOPED (`[^"'\\n]*`).

    An earlier revision let `[^"']*` span newlines, which matched ordinary
    Python `from x import y` lines and ORM `.where(...)` calls and reported
    two clean files as vulnerable. A security test that cries wolf gets
    muted, so precision here matters as much as coverage.
    """

    # An f-string handed straight to text()/execute() — the classic injection.
    FSTRING_SQL = re.compile(r"""(?:text|execute)\s*\(\s*(?:f["']|.*?%\s*\()""")

    # A SQL statement assembled with %-formatting or .format() on one line.
    # NB: the keyword alternation must not end in `\s` before a `\b` — in
    # "SELECT * FROM ..." the space is followed by `*`, both non-word, so there
    # is no word boundary there and the pattern silently never matches. The
    # self-test below caught exactly that.
    FORMATTED_SQL = re.compile(
        r"""["'][^"'\n]*\b(?:SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b[^"'\n]*["']\s*(?:%[^=]|\.format\()""",
        re.IGNORECASE,
    )

    def test_no_string_interpolated_sql_in_any_service(self) -> None:
        offenders: list[str] = []
        for service in _all_service_names():
            for path in _py_sources(service):
                for lineno, line in enumerate(
                    path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1
                ):
                    if self.FSTRING_SQL.search(line) or self.FORMATTED_SQL.search(line):
                        offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()[:80]}")
        assert not offenders, (
            "SQL appears to be built by string interpolation:\n"
            + "\n".join(offenders)
            + "\nUse bound parameters (:name) — SQLAlchemy's text() supports them."
        )

    def test_the_detector_actually_detects(self) -> None:
        """Guards the guard: proves the patterns above still match real attacks.

        Without this, a typo that makes the regex match nothing would turn the
        test above into a permanent silent pass.
        """
        should_flag = [
            'conn.execute(text(f"SELECT * FROM customer WHERE id = {cid}"))',
            'session.execute(f"DELETE FROM quote WHERE tenant_id = {tid}")',
            'q = "SELECT * FROM invoice WHERE id = %s" % ident',
            'q = "UPDATE payment SET x=1 WHERE id={}".format(pid)',
        ]
        for snippet in should_flag:
            assert self.FSTRING_SQL.search(snippet) or self.FORMATTED_SQL.search(snippet), (
                f"detector missed an injection pattern: {snippet}"
            )

        should_not_flag = [
            'from sqlalchemy import select, func',
            'stmt = stmt.where(CustomerModel.display_name.ilike(like))',
            'conn.execute(text("SELECT set_config(\'app.current_tenant\', :tid, true)"), {"tid": tid})',
            'text("SELECT * FROM outbox_claim_unprocessed(:limit)")',
        ]
        for snippet in should_not_flag:
            assert not (
                self.FSTRING_SQL.search(snippet) or self.FORMATTED_SQL.search(snippet)
            ), f"detector false-positives on safe code: {snippet}"

    def test_tenant_guc_is_set_with_a_bound_parameter(self) -> None:
        """set_config('app.current_tenant', ...) drives EVERY RLS policy.

        Interpolating the tenant id into that statement would let a crafted id
        terminate the string and set an arbitrary tenant — a direct, total
        tenant-isolation bypass.
        """
        checked = 0
        for service in _all_service_names():
            db_py = SERVICES / service / "app" / "infrastructure" / "db.py"
            if not db_py.is_file():
                continue
            text = db_py.read_text(encoding="utf-8")
            if "app.current_tenant" not in text:
                continue
            checked += 1
            assert re.search(r"set_config\('app\.current_tenant',\s*:", text), (
                f"{service}: app.current_tenant must be set via a bound parameter, "
                "never interpolated"
            )
        assert checked >= 5, f"expected several services to set the tenant GUC, found {checked}"


# ─── A01: RLS configuration ──────────────────────────────────────────────────


class TestRowLevelSecurity:
    def test_every_rls_table_has_a_tenant_scoping_policy(self) -> None:
        """A table with RLS enabled but no policy denies all access to
        non-owners and protects nothing from the owner — the worst of both.

        Policy NAMES vary by migration (`tenant_isolation` in the loop-driven
        ones, `<table>_tenant_iso` in 0013's payment tables), so this matches
        on the table a policy targets, not on its name.
        """
        enabled: set[str] = set()
        policied: set[str] = set()
        for path in sorted(MIGRATIONS.glob("*.sql")):
            sql = path.read_text(encoding="utf-8")
            enabled.update(re.findall(r"ALTER TABLE (\w+) ENABLE ROW LEVEL SECURITY", sql))
            policied.update(re.findall(r"CREATE POLICY \w+ ON (\w+)", sql))
            # Loop-driven forms: ARRAY['a','b'] applied to both statements.
            for arr in re.findall(r"ARRAY\[([^\]]+)\]", sql):
                names = {n.strip().strip("'") for n in arr.split(",")}
                if "ENABLE ROW LEVEL SECURITY" in sql:
                    enabled.update(names)
                if "CREATE POLICY" in sql:
                    policied.update(names)

        missing = enabled - policied
        assert not missing, (
            f"these tables have RLS enabled but NO policy at all: {sorted(missing)}."
        )

    def test_every_rls_policy_scopes_by_current_tenant(self) -> None:
        """The policy body is what actually isolates tenants. A policy that
        doesn't reference app_current_tenant() is decoration."""
        offenders: list[str] = []
        for path in sorted(MIGRATIONS.glob("*.sql")):
            sql = path.read_text(encoding="utf-8")
            for match in re.finditer(
                r"CREATE POLICY (\w+) ON (\w+)(.*?);", sql, re.DOTALL | re.IGNORECASE
            ):
                name, table, body = match.groups()
                if "app_current_tenant()" not in body:
                    offenders.append(f"{path.name}: policy {name} on {table}")
        assert not offenders, (
            "these RLS policies do not scope by app_current_tenant(), so they provide "
            "no tenant isolation:\n" + "\n".join(offenders)
        )

    def test_a_non_owner_application_role_exists(self) -> None:
        """`ENABLE ROW LEVEL SECURITY` does not apply to the table owner.

        Migrations create the tables, so the migration role owns them. If the
        services connect as that same role, every policy is bypassed and RLS
        provides no isolation whatsoever. A dedicated non-owner role is what
        makes the policies take effect.
        """
        sql = _strip_sql_comments(
            "\n".join(p.read_text(encoding="utf-8") for p in MIGRATIONS.glob("*.sql"))
        )
        assert "CREATE ROLE tradequote_app" in sql, (
            "no dedicated application role is created. Without one the app connects "
            "as the table owner and RLS is silently bypassed (T310 finding)."
        )

        # EVERY statement touching the role must be safe. Asserting only that
        # the safe spelling appears *somewhere* in the migrations let a mutated
        # CREATE ROLE ... BYPASSRLS pass, because a later ALTER still contained
        # the string "NOBYPASSRLS". Mutation testing caught that.
        statements = re.findall(r"(?:CREATE|ALTER) ROLE tradequote_app[^;]*", sql)
        assert statements, "no CREATE/ALTER ROLE statements found for tradequote_app"
        for stmt in statements:
            flat = " ".join(stmt.split())
            # (?<!NO) so a bare BYPASSRLS is caught while NOBYPASSRLS is not.
            assert not re.search(r"(?<!NO)BYPASSRLS", flat), (
                f"role statement grants BYPASSRLS, which defeats every tenant policy "
                f"in the database: {flat}"
            )
            assert not re.search(r"(?<!NO)SUPERUSER", flat), (
                f"role statement grants SUPERUSER, which bypasses RLS entirely: {flat}"
            )
            assert "NOBYPASSRLS" in flat, f"role statement must explicitly deny BYPASSRLS: {flat}"
            assert "NOSUPERUSER" in flat, f"role statement must explicitly deny SUPERUSER: {flat}"

    def test_application_role_has_no_ddl(self) -> None:
        sql = (MIGRATIONS / "0015_rls_app_role.sql").read_text(encoding="utf-8")
        grants = re.findall(r"GRANT ([A-Z, ]+) ON", sql)
        flat = {g.strip() for chunk in grants for g in chunk.split(",")}
        for forbidden in ("ALL PRIVILEGES", "TRUNCATE"):
            assert forbidden not in flat, (
                f"the application role is granted {forbidden}, which lets it bypass or "
                "dismantle row-level policies"
            )


# ─── A05: Security misconfiguration ──────────────────────────────────────────


class TestNoCommittedSecrets:
    """The dev defaults are allowed to exist in config files (guarded at
    startup). What must never appear is a real credential."""

    REAL_SECRET_PATTERNS = [
        (r"sk_live_[0-9a-zA-Z]{20,}", "Stripe live secret key"),
        (r"sk_test_[0-9a-zA-Z]{24,}", "Stripe test secret key"),
        (r"AKIA[0-9A-Z]{16}", "AWS access key id"),
        (r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----", "private key"),
        (r"ghp_[0-9a-zA-Z]{36}", "GitHub personal access token"),
        (r"xox[baprs]-[0-9a-zA-Z-]{10,}", "Slack token"),
        (r"AIza[0-9A-Za-z_-]{35}", "Google API key"),
    ]

    def test_no_real_credentials_committed(self) -> None:
        roots = [
            REPO_ROOT / "services",
            REPO_ROOT / "apps" / "api-gateway" / "src",
            REPO_ROOT / "infra",
            REPO_ROOT / "scripts",
        ]
        # Vendored trees are enormous and are not ours to audit here; walking
        # them turned this test into a multi-minute scan.
        skip_dirs = {".venv", "venv", "node_modules", "__pycache__", ".git", "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
        findings: list[str] = []
        for root in roots:
            for path in root.rglob("*"):
                if skip_dirs & set(path.parts):
                    continue
                if path.suffix not in {".py", ".ts", ".tsx", ".yml", ".yaml", ".json", ".sql", ".tf", ".sh"}:
                    continue
                if not path.is_file():
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                for pattern, label in self.REAL_SECRET_PATTERNS:
                    if re.search(pattern, text):
                        findings.append(f"{path.relative_to(REPO_ROOT)}: possible {label}")
        assert not findings, "possible real credentials committed:\n" + "\n".join(findings)

    def test_env_files_with_real_values_are_gitignored(self) -> None:
        ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        for pattern in (".env", "*.pem", "*.key"):
            assert pattern in ignored, f".gitignore must exclude {pattern}"


class TestServiceAuthBoundary:
    def test_no_service_except_auth_decodes_jwts(self) -> None:
        """Mirrors scripts/check_conventions.py, as a security invariant rather
        than a style rule: a service that decodes tokens itself can disagree
        with the gateway about who the caller is."""
        offenders: list[str] = []
        for service in _all_service_names():
            if service == "auth-service":
                continue
            for path in _py_sources(service):
                text = path.read_text(encoding="utf-8", errors="ignore")
                if re.search(r"^\s*import\s+jwt\b|^\s*from\s+jwt\b", text, re.MULTILINE):
                    offenders.append(str(path.relative_to(REPO_ROOT)))
                elif "jwt.decode(" in text:
                    offenders.append(str(path.relative_to(REPO_ROOT)))
        assert not offenders, (
            "these services decode JWTs themselves instead of trusting the gateway's "
            "x-tenant-id: " + ", ".join(offenders)
        )


# ─── A09: Logging & monitoring failures — security observability (T310b) ─────


class TestSecurityObservability:
    """The T310 review's A09 finding: the platform's defences worked and told
    nobody. These pin the observability itself, because an unobserved control
    and a missing control are indistinguishable during an incident.

    Behavioural coverage lives where it belongs — apps/api-gateway/test/
    security-metrics.test.ts drives real requests and reads the real /metrics
    exposition, and services/auth-service/tests/test_security_observability.py
    covers the audit writer. What is left here is the structural half: the
    things those cannot see, like statement ORDER within a function and the
    contents of a migration.
    """

    def test_identity_headers_are_observed_before_they_are_stripped(self, proxy_src: str) -> None:
        """Order matters and is invisible to a test that only checks the end
        state: after the `delete` calls there is nothing left to observe, so a
        caller could enumerate every tenant id in the platform, be correctly
        refused each time, and leave no trace anywhere.
        """
        observe = proxy_src.find("recordIdentityHeaderSpoofing(request)")
        assert observe != -1, (
            "plugins/proxy.ts no longer calls recordIdentityHeaderSpoofing — "
            "cross-tenant attempts would be stripped silently again (T310b)"
        )
        strip = proxy_src.find('delete headers["x-tenant-id"]')
        assert strip != -1, "the x-tenant-id strip itself is gone — that is the T310 C-2 defence"
        assert observe < strip, (
            "recordIdentityHeaderSpoofing must run BEFORE the identity headers are "
            "deleted; afterwards there is nothing left to observe"
        )

    def test_auth_failures_are_counted_at_the_gateway(self, auth_src: str) -> None:
        assert "recordAuthFailure(request" in auth_src, (
            "the gateway's 401 path no longer records a metric — a credential-stuffing "
            "run or a token-forgery attempt would be invisible again (T310b)"
        )

    def test_forgery_reasons_are_distinguishable_from_ordinary_expiry(self) -> None:
        """A wrong signature and a stale token are both '401' to a caller, but
        only one of them is an attack. Collapsing them into a single reason is
        what made the C-1 dev-secret scenario undetectable, so the distinction
        is pinned here rather than left to a reviewer to notice.
        """
        src = _strip_ts_comments((GATEWAY_SRC / "auth.ts").read_text(encoding="utf-8"))
        for reason in ("invalid_signature", "invalid_algorithm", "expired_token"):
            assert f'"{reason}"' in src, f"auth failure reason {reason!r} is gone from auth.ts"

    def test_the_audit_log_is_append_only_for_the_application_role(self) -> None:
        """An audit log the application can rewrite is worthless against the
        one attacker it exists to catch — the one who reached the application.

        0015 grants SELECT/INSERT/UPDATE/DELETE on ALL TABLES to
        `tradequote_app`; 0016 must narrow that back for this table. TRUNCATE
        is included because it bypasses row-level DELETE policies entirely.
        """
        sql = _strip_sql_comments(
            (MIGRATIONS / "0016_security_audit.sql").read_text(encoding="utf-8")
        )
        revokes = [
            line for line in sql.splitlines() if "REVOKE" in line.upper() and "auth_audit_log" in line
        ]
        assert revokes, "0016 does not REVOKE anything on auth_audit_log"
        revoked = " ".join(revokes).upper()
        for privilege in ("UPDATE", "DELETE", "TRUNCATE"):
            assert privilege in revoked, (
                f"{privilege} is still granted to tradequote_app on auth_audit_log — "
                "the audit log is editable by the application"
            )
        assert "TRADEQUOTE_APP" in revoked, "the REVOKE does not name the application role"

    def test_privileged_actions_are_actually_written(self) -> None:
        """`auth_audit_log` existed from migration 0002 and nothing ever wrote
        a row to it — a control that was on the schema diagram and absent in
        reality. This fails if that regresses.
        """
        routes = _auth_routes_src()
        assert "audit.record(" in routes, "auth-service no longer writes audit rows on success"
        assert "audit.record_isolated(" in routes, (
            "auth-service no longer writes an audit row for FAILED logins — those are "
            "the only rows anyone pages on, and they roll back with the failed "
            "transaction unless written separately"
        )

    def test_login_does_not_leak_why_it_failed(self) -> None:
        """The failure reason is recorded for the tenant and for Prometheus,
        and must never reach the caller: an endpoint that distinguishes 'no
        such user' from 'wrong password' is an account-enumeration oracle.
        """
        routes = _auth_routes_src()
        login = routes[routes.index("def login(") : routes.index("def me(")]
        raises = [line for line in login.splitlines() if "HTTP_401_UNAUTHORIZED" in line]
        assert raises, "the login handler no longer raises a 401"
        for line in raises:
            assert "exc.reason" not in line and "str(exc)" not in line, (
                "the 401 body carries the failure reason — this turns /login into an "
                f"account-enumeration oracle: {line.strip()}"
            )

    def test_reading_the_audit_log_requires_an_administrative_role(self) -> None:
        routes = _auth_routes_src()
        assert "AUDIT_READER_ROLES" in routes, (
            "the audit-log endpoint no longer checks roles — every login attempt and "
            "attempted email in the tenant would be readable by any authenticated user"
        )
        # The set must stay narrow. This log exposes the attempted addresses
        # from every failed login, which is exactly what an attacker holding
        # one low-privilege account would want next.
        match = re.search(r"AUDIT_READER_ROLES\s*=\s*frozenset\(\{([^}]*)\}\)", routes)
        assert match, "AUDIT_READER_ROLES is no longer a literal frozenset"
        roles = {r.strip().strip("\"'") for r in match.group(1).split(",") if r.strip()}
        assert roles == {"owner", "admin"}, f"audit-log readers widened to {sorted(roles)}"

    def test_security_alerts_page_on_events_with_no_benign_cause(self) -> None:
        """The metrics are useless if nothing evaluates them. Pinned here and
        not only in tests/infra because the *severity* is a security decision:
        a cross-tenant probe that files a business-hours ticket is a finding
        somebody reads on Monday.
        """
        import yaml

        rules_file = (
            REPO_ROOT / "infra" / "monitoring" / "prometheus" / "rules" / "security-metrics.yml"
        )
        assert rules_file.is_file(), "the T310b security alert rules are gone"
        doc = yaml.safe_load(rules_file.read_text(encoding="utf-8"))
        alerts = {
            rule["alert"]: rule
            for group in doc["groups"]
            for rule in group.get("rules", [])
            if "alert" in rule
        }
        for name in (
            "TokenForgeryAttempt",
            "CrossTenantAccessAttempt",
            "CredentialStuffingSuspected",
            "HighAuthFailureRate",
            "AuditLogWriteFailures",
        ):
            assert name in alerts, f"security alert {name} is missing"
        for name in ("TokenForgeryAttempt", "CrossTenantAccessAttempt"):
            assert alerts[name]["labels"]["severity"] == "page", (
                f"{name} must page — it has no benign cause"
            )

"""Security metrics for the identity service (T310b / M27 — OWASP A09).

The gateway counts *token* failures (apps/api-gateway/src/plugins/security-metrics.ts).
This counts *credential* failures, which only auth-service can see: the gateway
never touches `/v1/auth/login`'s body, so a password-guessing run is invisible
to it — every one of those requests is a well-formed, unauthenticated POST to a
public route, indistinguishable from a real user signing in.

Registered against `prometheus_client`'s default REGISTRY, which is the same
one `prometheus-fastapi-instrumentator` exposes at `/metrics` (see
observability.py) — so these ride the existing `app-metrics` scrape job with no
new endpoint, port, or scrape config.

Cardinality: every label here is drawn from a closed set defined in this
module. None is derived from request input. That is deliberate — these
counters are driven by *unauthenticated* traffic, so any attacker-controlled
label would be a remote "make Prometheus allocate a new time series" primitive.
The attempted email is far too high-cardinality to be a label; it goes in the
audit-log row instead (app/application/audit.py), which is queryable per tenant
and is the right place to answer "one account or ten thousand".
"""

from __future__ import annotations

from enum import StrEnum

from prometheus_client import Counter


class LoginFailureReason(StrEnum):
    """Why a login was refused. Closed set — used as a metric label.

    Kept coarser than the internal control flow on purpose. `UNKNOWN_USER` and
    `BAD_PASSWORD` are *both* recorded because operators need to tell a
    credential-stuffing run (many unknown users) from a targeted brute force
    (one known user, many bad passwords) — but note this distinction is only
    ever exposed on the metrics endpoint and in the tenant's own audit log,
    never in an HTTP response. The API keeps answering a flat "invalid
    credentials" so it stays a non-oracle for account enumeration.
    """

    UNKNOWN_TENANT = "unknown_tenant"
    UNKNOWN_USER = "unknown_user"
    BAD_PASSWORD = "bad_password"
    INACTIVE_USER = "inactive_user"
    MFA_FAILED = "mfa_failed"


login_attempts_total = Counter(
    "auth_login_attempts_total",
    "Login attempts handled by auth-service, by result.",
    ["result"],
)

login_failures_total = Counter(
    "auth_login_failures_total",
    "Failed logins by reason. The denominator is auth_login_attempts_total.",
    ["reason"],
)

privileged_actions_total = Counter(
    "security_privileged_actions_total",
    "Privileged actions recorded to the audit log, by action and outcome.",
    ["action", "outcome"],
)

audit_write_failures_total = Counter(
    "security_audit_write_failures_total",
    (
        "Audit-log writes that raised. Non-zero means privileged actions are "
        "happening without leaving a record — the audit log is failing silently."
    ),
)


def record_login_success() -> None:
    login_attempts_total.labels(result="success").inc()


def record_login_failure(reason: LoginFailureReason) -> None:
    login_attempts_total.labels(result="failure").inc()
    login_failures_total.labels(reason=str(reason)).inc()

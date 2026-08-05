"""Tests for T309b observability wiring: /metrics, Sentry, OTel — all opt-in.

`app.main` is instrumented exactly once per test process (at import time,
with SENTRY_DSN/OTEL_EXPORTER_OTLP_ENDPOINT unset, same as every dev/CI run),
so the Sentry/OTel opt-in paths are exercised directly against the private
helpers rather than by re-running the full `instrument()` — calling
`Instrumentator().add(default()).instrument(app)` a second time in the same
process re-registers the same-named collectors into prometheus_client's
global registry and raises `ValueError: Duplicated timeseries`.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.infrastructure import observability
from app.main import app


def test_metrics_endpoint_exposes_prometheus_format() -> None:
    client = TestClient(app)
    client.get("/health")  # generate at least one instrumented request first
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "http_requests_total" in resp.text


def test_metrics_endpoint_excluded_from_openapi_schema() -> None:
    schema = app.openapi()
    assert "/metrics" not in schema["paths"]


def test_sentry_is_a_no_op_when_dsn_unset() -> None:
    # Must not raise — this is the default state in every local/dev/test env.
    observability._instrument_sentry("", "test-service", "test")


def test_sentry_initializes_when_dsn_set() -> None:
    import sentry_sdk

    observability._instrument_sentry("https://public@sentry.example.com/1", "test-service", "test")
    try:
        assert sentry_sdk.get_client().is_active()
    finally:
        sentry_sdk.get_client().close()


def test_tracing_is_a_no_op_when_endpoint_unset() -> None:
    # Must not raise, and must not touch the global tracer provider.
    observability._instrument_tracing(FastAPI(), "test-service", "")


def test_tracing_initializes_when_endpoint_set() -> None:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

    observability._instrument_tracing(FastAPI(), "test-service", "http://localhost:4318/v1/traces")
    assert isinstance(trace.get_tracer_provider(), TracerProvider)

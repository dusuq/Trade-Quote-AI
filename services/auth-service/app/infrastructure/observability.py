"""Observability: Prometheus `/metrics`, OpenTelemetry traces, Sentry (T309b / M24).

Ported (not imported) into every service's app/infrastructure/ — this repo has
no shared Python runtime package (see integration-service's http.py precedent
for the same "ported, not imported" call), so keep this file in sync by hand
across services rather than reaching for a shared import that doesn't exist
here. A drift here is a missing metric/trace/error report in one service, not
a broken build — nothing enforces the copies stay identical.

Every piece is opt-in based on config, so a service with neither SENTRY_DSN
nor OTEL_EXPORTER_OTLP_ENDPOINT set (every local dev environment, every test
run) boots exactly as it did before T309b:
  - /metrics is always mounted — Prometheus scraping needs no external
    endpoint to work, so there's nothing to gate it on.
  - OpenTelemetry tracing only starts if OTEL_EXPORTER_OTLP_ENDPOINT is set.
  - Sentry only initializes if SENTRY_DSN is set.
"""

from __future__ import annotations

from fastapi import FastAPI


def instrument(
    app: FastAPI,
    *,
    service_name: str,
    service_env: str,
    sentry_dsn: str,
    otel_endpoint: str,
) -> None:
    """Wire `/metrics`, OTel tracing, and Sentry into `app`.

    Call immediately after constructing `app = FastAPI(...)`, before routers
    are included — Instrumentator's middleware must be registered before the
    app starts serving requests, and this keeps that ordering enforced at a
    single call site rather than relying on main.py's line order.
    """
    _instrument_metrics(app)
    _instrument_sentry(sentry_dsn, service_name, service_env)
    _instrument_tracing(app, service_name, otel_endpoint)


def _instrument_metrics(app: FastAPI) -> None:
    from prometheus_fastapi_instrumentator import Instrumentator
    from prometheus_fastapi_instrumentator.metrics import default

    # `Instrumentator().instrument(app)` alone registers NO metrics — its
    # `instrumentations` list starts empty, and nothing populates it
    # implicitly. `.add(default())` is what actually gets request
    # count/latency/size series; omitting it silently ships a /metrics
    # endpoint that always returns an empty body.
    #
    # excluded_handlers keeps /health and /metrics themselves out of the
    # request-count/latency series — a Fly health check hitting /health every
    # 15s would otherwise dominate every histogram with noise from a route
    # that isn't part of the application's actual traffic.
    Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        excluded_handlers=["/health", "/metrics"],
    ).add(default()).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


def _instrument_sentry(dsn: str, service_name: str, service_env: str) -> None:
    if not dsn:
        return

    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=service_env,
        server_name=service_name,
        # A fixed, conservative trace sample rate for Sentry's own APM spans —
        # unrelated to OTel's traces above, which are unsampled at this layer.
        traces_sample_rate=0.1,
        # This is a multi-tenant SaaS; request bodies/headers can carry a
        # customer's PII (name, address, phone). Sentry's default PII capture
        # is an opt-in leak surface across every tenant, so it stays off.
        send_default_pii=False,
    )


def _instrument_tracing(app: FastAPI, service_name: str, otel_endpoint: str) -> None:
    if not otel_endpoint:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otel_endpoint)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)

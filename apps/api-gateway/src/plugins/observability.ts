/**
 * Observability: Prometheus `/metrics`, OpenTelemetry traces, Sentry (T309b / M24).
 *
 * Every piece is opt-in based on config, mirroring the pattern ported across
 * every Python service's app/infrastructure/observability.py — a gateway with
 * neither SENTRY_DSN nor OTEL_EXPORTER_OTLP_ENDPOINT set (every local dev
 * environment, every test run) boots exactly as it did before T309b:
 *   - /metrics is always mounted — Prometheus scraping needs no external
 *     endpoint to work.
 *   - OpenTelemetry tracing only starts if OTEL_EXPORTER_OTLP_ENDPOINT is set.
 *   - Sentry only initializes if SENTRY_DSN is set.
 *
 * Tracing is deliberately NOT the auto-instrumentation package
 * (`@opentelemetry/auto-instrumentations-node`) — that relies on a
 * `--require`/loader hook patching `node:http` before Fastify's own import
 * evaluates, which this repo's plain `tsx`/`node dist/index.js` entrypoints
 * don't set up, and getting it wrong silently instruments nothing. Instead
 * this creates one server span per request by hand and injects a W3C
 * `traceparent` header into the outgoing proxy call (see
 * `injectTraceHeaders`, used by plugins/proxy.ts) so a trace started here
 * continues into whichever FastAPI service handles the request.
 */
import type { FastifyInstance, FastifyRequest } from "fastify";
import fp from "fastify-plugin";
import client from "prom-client";
import { type Span, ROOT_CONTEXT, SpanKind, SpanStatusCode, trace } from "@opentelemetry/api";
import { W3CTraceContextPropagator } from "@opentelemetry/core";
import { Resource } from "@opentelemetry/resources";
import { ATTR_SERVICE_NAME } from "@opentelemetry/semantic-conventions";
import { BatchSpanProcessor } from "@opentelemetry/sdk-trace-base";
import { NodeTracerProvider } from "@opentelemetry/sdk-trace-node";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import * as Sentry from "@sentry/node";

export interface ObservabilityOptions {
  serviceName: string;
  serviceEnv: string;
  sentryDsn: string;
  otelEndpoint: string;
}

declare module "fastify" {
  interface FastifyRequest {
    otelSpan?: Span;
  }
}

// Module-level (not per-plugin-registration): prom-client throws on a
// duplicate metric name in the same registry, and buildServer() is called
// once per test in this repo's suite — these must be created exactly once
// per process, same reasoning as the collectDefaultMetrics guard below.
const httpRequestsTotal = new client.Counter({
  name: "http_requests_total",
  help: "Total number of requests by method, route and status code.",
  labelNames: ["method", "route", "status_code"],
});

const httpRequestDuration = new client.Histogram({
  name: "http_request_duration_seconds",
  help: "Request duration in seconds by method and route.",
  labelNames: ["method", "route"],
  buckets: [0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
});

let defaultMetricsCollected = false;

const propagator = new W3CTraceContextPropagator();

/**
 * The Fastify *route pattern* (`/v1/quotes/*`), never the concrete URL.
 *
 * Exported because plugins/security-metrics.ts labels its own counters the
 * same way, and the two must agree: the raw URL carries ids, so using it as a
 * label would give Prometheus one series per object — unbounded cardinality
 * on a metric an attacker can drive.
 */
export function routeLabel(request: FastifyRequest): string {
  return request.routeOptions?.url ?? request.url.split("?")[0] ?? "unknown";
}

export default fp(
  async function observabilityPlugin(app: FastifyInstance, opts: ObservabilityOptions) {
    registerMetrics(app);
    registerSentry(opts);
    registerTracing(app, opts);
  },
  { name: "observability-plugin" },
);

function registerMetrics(app: FastifyInstance): void {
  if (!defaultMetricsCollected) {
    client.collectDefaultMetrics();
    defaultMetricsCollected = true;
  }

  app.addHook("onResponse", async (request, reply) => {
    // A Fly health check or Prometheus's own scrape hitting these every few
    // seconds would otherwise dominate the series with noise that isn't the
    // application's actual traffic — same exclusion as the Python services.
    if (request.url === "/metrics" || request.url === "/health") return;
    const route = routeLabel(request);
    httpRequestsTotal.inc({ method: request.method, route, status_code: reply.statusCode });
    httpRequestDuration.observe({ method: request.method, route }, reply.elapsedTime / 1000);
  });

  app.get("/metrics", { logLevel: "silent" }, async (_request, reply) => {
    reply.header("content-type", client.register.contentType);
    return client.register.metrics();
  });
}

function registerSentry(opts: ObservabilityOptions): void {
  if (!opts.sentryDsn) return;

  Sentry.init({
    dsn: opts.sentryDsn,
    environment: opts.serviceEnv,
    serverName: opts.serviceName,
    tracesSampleRate: 0.1,
    // This gateway proxies a multi-tenant SaaS's entire authenticated
    // surface; request bodies/headers can carry a customer's PII. Sentry's
    // default PII capture is an opt-in leak surface across every tenant.
    sendDefaultPii: false,
  });
}

function registerTracing(app: FastifyInstance, opts: ObservabilityOptions): void {
  if (!opts.otelEndpoint) return;

  const provider = new NodeTracerProvider({
    resource: new Resource({ [ATTR_SERVICE_NAME]: opts.serviceName }),
    spanProcessors: [new BatchSpanProcessor(new OTLPTraceExporter({ url: opts.otelEndpoint }))],
  });
  provider.register();
  const tracer = trace.getTracer(opts.serviceName);

  app.addHook("onRequest", async (request) => {
    request.otelSpan = tracer.startSpan(`${request.method} ${routeLabel(request)}`, {
      kind: SpanKind.SERVER,
      attributes: { "http.method": request.method, "http.target": request.url },
    });
  });

  app.addHook("onResponse", async (request, reply) => {
    const span = request.otelSpan;
    if (!span) return;
    span.setAttribute("http.status_code", reply.statusCode);
    if (reply.statusCode >= 500) span.setStatus({ code: SpanStatusCode.ERROR });
    span.end();
  });
}

/**
 * Inject a W3C `traceparent` header derived from the request's server span
 * into an outgoing proxy call, so the trace continues into the downstream
 * FastAPI service instead of starting a new, disconnected one there.
 *
 * A no-op when tracing isn't configured (`request.otelSpan` is unset) —
 * callers don't need to check `otelEndpoint` themselves.
 */
export function injectTraceHeaders(request: FastifyRequest, headers: Record<string, string>): void {
  const span = request.otelSpan;
  if (!span) return;
  propagator.inject(trace.setSpan(ROOT_CONTEXT, span), headers, {
    set: (carrier, key, value) => {
      carrier[key] = value;
    },
  });
}

import json
import logging
import os
import time
from datetime import datetime, timezone

from opentelemetry import trace
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.propagate import extract
from prometheus_client import CollectorRegistry, Counter, Histogram
from prometheus_client.asgi import make_asgi_app


PAYMENTS = Counter("payment_committed", "Payments committed to PostgreSQL", ["status"], registry=None)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        context = trace.get_current_span().get_span_context()
        return json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": f"{context.trace_id:032x}" if context.is_valid else "",
            "span_id": f"{context.span_id:016x}" if context.is_valid else "",
        })


def tracer_for(service):
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return None
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(BatchSpanProcessor(
        OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")
    ))
    logs = LoggerProvider(resource=Resource.create({"service.name": service}))
    logs.add_log_record_processor(BatchLogRecordProcessor(
        OTLPLogExporter(endpoint=f"{endpoint.rstrip('/')}/v1/logs")
    ))
    handler = LoggingHandler(level=logging.INFO, logger_provider=logs)
    handler.setFormatter(JsonFormatter())
    logging.getLogger(f"{service}.http").addHandler(handler)
    if service == "api":
        logging.getLogger("app").addHandler(handler)
    return provider


class HttpTelemetry:
    def __init__(self, app, service, requests, duration, provider):
        self.app = app
        self.service = service
        self.requests = requests
        self.duration = duration
        self.tracer = provider.get_tracer(__name__) if provider else None
        self.provider = provider
        self.logger = logging.getLogger(f"{service}.http")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"].rstrip("/") == "/metrics":
            await self.app(scope, receive, send)
            return

        if self.tracer is None:
            await self.observe(scope, receive, send)
            return
        headers = {key.decode("latin1"): value.decode("latin1") for key, value in scope["headers"]}
        with self.tracer.start_as_current_span(
            scope["method"], context=extract(headers), kind=SpanKind.SERVER,
            record_exception=False, set_status_on_exception=False,
        ) as span:
            await self.observe(scope, receive, send, span)

    async def observe(self, scope, receive, send, span=None):
        started = time.monotonic()
        status = 500

        async def send_response(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_response)
        finally:
            route = getattr(scope.get("route"), "path", "unmatched")
            method = scope["method"]
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                method = "OTHER"
            if span is not None:
                span.update_name(f"{method} {route}")
                span.set_attribute("http.route", route)
                span.set_attribute("http.request.method", method)
                span.set_attribute("http.response.status_code", status)
                if status >= 500:
                    span.set_status(Status(StatusCode.ERROR))
            context = trace.get_current_span().get_span_context()
            exemplar = {"trace_id": f"{context.trace_id:032x}"} if context.is_valid and context.trace_flags.sampled else None
            labels = (self.service, method, route, str(status))
            self.requests.labels(*labels).inc()
            self.duration.labels(*labels).observe(time.monotonic() - started, exemplar=exemplar)
            if self.provider:
                self.logger.log(
                    logging.ERROR if status >= 500 else logging.INFO,
                    "%s %s %s", method, route, status,
                )


def configure_http(app, service, provider):
    registry = CollectorRegistry()
    if service == "api":
        registry.register(PAYMENTS)
    labels = ("service", "method", "route", "status")
    requests = Counter("payment_http_requests", "HTTP requests", labels, registry=registry)
    duration = Histogram("payment_http_duration_seconds", "HTTP duration", labels, registry=registry)
    app.mount("/metrics", make_asgi_app(registry), name="metrics")
    app.add_middleware(
        HttpTelemetry, service=service, requests=requests, duration=duration, provider=provider,
    )
    return registry

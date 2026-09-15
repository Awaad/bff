# Local Infrastructure

This Compose stack is for local development and integration tests only.

Services:

- PostgreSQL 18.6
- RabbitMQ 4.3.5 with the management plugin
- Valkey 9.1.2
- OpenTelemetry Collector Contrib 0.160.0

All published ports bind to `127.0.0.1`.

## Start

```bash
cp .env.example .env
docker compose up -d
python scripts/infra/smoke.py
```

## Stop

```bash
docker compose down
```

To also remove local state:

```bash
docker compose down -v
```

Do not use `down -v` if you need to preserve local database/broker/cache state.

## OpenTelemetry

The development Collector accepts OTLP on:

- gRPC: `127.0.0.1:4317`
- HTTP: `127.0.0.1:4318`

The health endpoint is:

```text
http://127.0.0.1:13133/
```

The development exporter is `debug`; production exporters are intentionally not configured here.

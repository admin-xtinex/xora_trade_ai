# Docker architecture

Not a single-container app. Local Compose mirrors production roles.

## Services

```
            +-------------+         +-------------+
 client --> | api :8000   |         | worker      |
            | FastAPI     |         | cycles      |
            +------+------+         +------+------+
                   |                       |
                   +-----------+-----------+
                               |
                        +------+------+
                        | postgres 16 |
                        | :5432       |
                        +------+------+
                               |
                        +------+------+
                        | pgadmin     |   optional, profile=dev
                        | :5050       |
                        +-------------+
```

## Compose roles

| Service | Image / build | Command | Owns |
|---|---|---|---|
| `api` | `Dockerfile.api` | `uvicorn xora.main:app` | HTTP only |
| `worker` | `Dockerfile.worker` | `python -m xora.worker` | prediction + validation loops |
| `postgres` | `postgres:16` | official entrypoint | data |
| `pgadmin` | `dpage/pgadmin4` | official | local DX |

API and worker share one code mount / image family but **different entrypoints**. Do not start the scheduler inside uvicorn.

## Networks and volumes

- internal bridge network `xora`
- named volume `xora_pg_data`
- secrets via env file, never baked into images

## Health

- postgres: `pg_isready`
- api: `GET /api/v1/health`
- worker: heartbeat row in `system_configuration` or `/tmp/worker_heartbeat` checked by Docker HEALTHCHECK

## What is intentionally absent

- Redis (add later if pub/sub or rate-limit coordination is needed)
- a bundled frontend
- an execution / order worker

## Draft Compose (spec only)

See repository root `docker-compose.yml`. It is a target definition. Images will not build until implementation is approved and Dockerfiles exist.

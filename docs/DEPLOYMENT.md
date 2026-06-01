# Production Deployment

This project runs best as Docker Compose services on a VPS or cloud server.

## Server

- Ubuntu 22.04 or 24.04
- At least 2GB RAM for a small beta
- Open inbound ports: 22, 80, 443
- Docker and Docker Compose plugin

## Environment

Copy `.env.production.example` to `.env.production` on the server and fill real values.
Do not commit `.env.production`.

For first beta on a small server, keep:

- `MAX_ACTIVE_JOBS_PER_USER=1`
- `MAX_VIDEO_DURATION_SECONDS=600` or less
- `METIS_PARALLEL_CHUNKS=2`

## Run

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.production ps
curl http://127.0.0.1/health
```

## Restricted-Network Server

Use the optional egress overlay when the server cannot reach Google, YouTube, or
AvalAI directly. The overlay connects only `backend` and `worker` to an existing
Docker network named `mioondar-egress` and sends their environment-aware HTTP
clients through `http://gluetun:8888`.

The overlay also gives backend and frontend image builds controlled proxy
access for package installation. This avoids making the host route depend on
the VPN.

Metis and Aparat clients intentionally keep their direct-network behavior in
application code. Postgres and Redis also remain direct through `NO_PROXY`.

```bash
docker network inspect mioondar-egress
docker compose \
  -f docker-compose.prod.yml \
  -f docker-compose.egress.yml \
  --env-file .env.production \
  up -d --build
docker compose \
  -f docker-compose.prod.yml \
  -f docker-compose.egress.yml \
  --env-file .env.production \
  ps
```

The Gluetun HTTP and SOCKS5 ports must stay bound to server loopback only. Do
not expose unauthenticated proxy ports to the public internet.

See [`RESTRICTED_NETWORK_EGRESS.md`](./RESTRICTED_NETWORK_EGRESS.md) for the
server-local Gluetun runbook and health checks.

## Google OAuth

Add the production callback in Google Cloud:

```text
http://YOUR_SERVER_IP_OR_DOMAIN/auth/google/callback
```

Use HTTPS before wider testing. For an IP-only smoke test, HTTP can be used briefly.

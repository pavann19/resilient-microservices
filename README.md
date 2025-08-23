
# Resilient Microservices Deployment Platform

**Stack:** FastAPI, Docker, Docker Compose, Redis, GitHub Actions (CI/CD)

## What this demo shows
- 6 services (gateway, service_a, service_b, service_c, fallback, redis)
- **Fault-tolerance**: retries + fallback if `service_b` fails
- **Health checks** for all services
- **Public demo ready**: run locally via Docker Compose, deploy on Render/Railway

## Quickstart (Local)
```bash
docker compose up --build
# Open the gateway aggregate endpoint
curl http://localhost:8080/aggregate
```

## Simulate failures
Edit `FAIL_RATE` in `docker-compose.yml` under `service_b` (e.g., 0.6) and re-run.

## Suggested Render Deployment
- Create a new **Web Service** for each service (gateway, service_a, service_b, service_c, fallback).
- Use **Docker** as runtime; point each service to its subfolder (`./gateway`, `./service_a`, etc.).
- Set environment variables in Render to internal service URLs (e.g., `SERVICE_A_URL=https://service-a.onrender.com`).
- Expose only the **gateway** publicly; others can be internal if you use a private network (or keep them public for demo simplicity).

## GitHub Actions (CI/CD)
Add a workflow that runs tests/lint and can hit the Render Deploy Hook to trigger redeploy.
Create a **Deploy Hook** in Render for each service and add secrets in GitHub:
- `RENDER_HOOK_GATEWAY`, `RENDER_HOOK_SERVICE_A`, etc.

See `.github/workflows/ci.yml` for a minimal example.

## Endpoints
- `GET /aggregate` (gateway) → calls A + B, falls back if B fails
- `GET /health` on each service
- `GET /service_a/hello` (internal, shown via gateway in aggregate)
- `GET /service_c/echo/<msg>`

## Repo structure
```
project1-resilient-microservices/
  docker-compose.yml
  gateway/
  service_a/
  service_b/
  service_c/
  fallback/
  .github/workflows/ci.yml
  README.md
```

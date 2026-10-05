---
name: docker-compose
description: 'Docker Compose files for local dev and small deployments: services, named volumes, env files, healthchecks with depends_on conditions, and validation with docker compose config without bringing a stack up.'
when_to_use: Use when writing or reviewing compose.yaml / docker-compose.yml, Dockerfiles for those services, healthchecks or local dev databases.
metadata:
  schema: 1
  category: general
  surfaces:
  - backend
  platforms:
  - linux
  - darwin
  - windows
  triggers:
    keywords:
    - docker compose
    - docker-compose
    - compose file
    - compose.yaml
    - docker-compose.yml
    - healthcheck
    - service_healthy
    - depends_on
    - dockerfile
    - named volume
    - container
    intents: []
---
# Docker Compose

**Never run `docker compose up` (or `start`, `run`, `restart`) unless the user asks.**
Bringing a stack up starts servers, binds ports and can write into volumes; validation
does not need it.

## File shape

- Name it `compose.yaml` (or keep the repo's existing `docker-compose.yml`); no top-level
  `version:` key (obsolete in Compose v2).
- One service per process; build app images from a Dockerfile, pin third-party images to
  a major.minor tag (`mongo:7.0`), never `latest`.
- Data in **named volumes** (`volumes: { mongo-data: {} }`), source code in bind mounts
  only for dev hot-reload.
- Config through `env_file: .env` plus `environment:` for non-secret values; commit a
  `.env.example`, never the `.env`. Secrets do not go into the compose file or the image.
- Publish only the ports a person needs from the host; services talk over the default
  network by service name (`mongodb://mongo:27017/app`).

## Healthchecks and start order

```yaml
services:
  mongo:
    image: mongo:7.0
    volumes: [mongo-data:/data/db]
    healthcheck:
      test: ["CMD", "mongosh", "--quiet", "--eval", "db.adminCommand('ping').ok"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s
  api:
    build: ./server
    env_file: .env
    depends_on:
      mongo:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:3000/health"]
      interval: 15s
      timeout: 5s
      retries: 3
volumes:
  mongo-data: {}
```

- `depends_on` without `condition: service_healthy` only orders container start, not
  readiness.
- The healthcheck command must exist inside the image (`wget` is in Alpine/BusyBox,
  `curl` often is not); the app exposes a cheap health route that does not hit every
  dependency.

## Dockerfile for the app service

Multi-stage: install with the lockfile (`npm ci`), build, then copy only the runtime
output and production deps into a slim final stage; run as a non-root user; a
`.dockerignore` excludes `node_modules`, `.env`, `.git`, build output.

## Validate without starting anything

```bash
docker compose config --quiet          # schema + interpolation check, exits non-zero on error
docker compose config --services       # the services it will create
hadolint Dockerfile                     # if installed
```

`docker compose build` is acceptable when the user wants the image checked; it starts no
containers. Report what still needs a real `up` (healthchecks passing, ports reachable)
as the user's step.

## Not this skill

CI pipelines (`ci-cd-and-automation`), production rollout and rollback
(`shipping-and-launch`), Kubernetes manifests.

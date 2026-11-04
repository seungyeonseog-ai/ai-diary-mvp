#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")/.."
unset OPENAI_API_KEY REAL_OPENAI_API_KEY SECRET_KEY MATABUS_IMAGE WEB_PORT OPENAI_MODEL COMPOSE_PROJECT_NAME
exec docker compose --env-file .local-check/docker-validation/real.env \
  --project-name matabus-validation \
  -f docker-compose.yml -f docker-compose.validation.yml -f docker-compose.real-validation.yml "$@"

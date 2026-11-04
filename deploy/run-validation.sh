#!/bin/sh
# 명시적으로 별도 프로젝트/볼륨/합성 AI 설정만 사용한다.
set -eu
cd -- "$(dirname -- "$0")/.."
# 상속된 실키/운영 포트가 검증 env-file보다 우선하지 않도록 한다.
unset OPENAI_API_KEY SECRET_KEY MATABUS_IMAGE WEB_PORT OPENAI_MODEL COMPOSE_PROJECT_NAME
exec docker compose --env-file .local-check/docker-validation/validation.env \
  --project-name matabus-validation \
  -f docker-compose.yml -f docker-compose.validation.yml "$@"

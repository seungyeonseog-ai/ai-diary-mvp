#!/bin/sh
set -eu
if ! docker info >/dev/null 2>&1; then
  # 전경 세션을 유지해 WSL 유휴 종료로 소켓이 사라지지 않게 한다.
  exec dockerd --host=unix:///var/run/docker.sock
fi
docker info --format 'Docker={{.ServerVersion}} MemoryBytes={{.MemTotal}} CPUs={{.NCPU}}'
docker compose version
if command -v systemctl >/dev/null 2>&1; then
  systemctl is-enabled docker.service docker.socket containerd.service || true
fi

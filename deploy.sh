#!/bin/sh
# 서버에서 로컬 빌드/기동한다. Hub 로그인/푸시는 실행하지 않는다.
set -eu
cd -- "$(dirname -- "$0")"
exec python3 -m deploy.compose start "$@"

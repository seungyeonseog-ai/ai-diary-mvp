#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")/../.."
docker run --rm -i --network none matabus-local:pilot python -B - < tests/deployment/check_image.py
docker run --rm -i --network none matabus-local:pilot python -B - < tests/test_deployment.py

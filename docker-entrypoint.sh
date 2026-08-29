#!/bin/sh
set -eu

python -m apps.provider_preflight
exec "$@"

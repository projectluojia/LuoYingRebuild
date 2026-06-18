#!/usr/bin/env bash
set -euo pipefail

directus_status="$(curl -fsS http://localhost:8055/server/ping)"
ragflow_web_code="$(curl -o /dev/null -s -w '%{http_code}' http://localhost:8088 || true)"
ragflow_api_code="$(curl -o /dev/null -s -w '%{http_code}' http://localhost:9380 || true)"

echo "Directus /server/ping: $directus_status"
echo "RAGFlow web HTTP status: $ragflow_web_code"
echo "RAGFlow API HTTP status: $ragflow_api_code"

test "$directus_status" = "pong"
test "$ragflow_web_code" != "000" -o "$ragflow_api_code" != "000"

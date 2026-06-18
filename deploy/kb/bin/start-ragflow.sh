#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
RAGFLOW_DIR="$ROOT_DIR/deploy/kb/ragflow"

if [[ ! -f "$RAGFLOW_DIR/.env" ]]; then
  cp "$RAGFLOW_DIR/.env.example" "$RAGFLOW_DIR/.env"
fi

python "$ROOT_DIR/scripts/configure_ragflow_local_env.py" --env-file "$RAGFLOW_DIR/.env"

(
  cd "$RAGFLOW_DIR"
  docker compose -p luoying-ragflow up -d
)

docker network connect luoying_app_network luoying-ragflow-ragflow-cpu-1 >/dev/null 2>&1 || true

for _ in $(seq 1 180); do
  if curl -fsS http://localhost:8088 >/dev/null || curl -fsS http://localhost:9380 >/dev/null; then
    break
  fi
  sleep 5
done

curl -fsS http://localhost:8088 >/dev/null || curl -fsS http://localhost:9380 >/dev/null

PYTHONPATH="$ROOT_DIR/src" python "$ROOT_DIR/scripts/configure_local_kb_env.py" \
  --env-file "$ROOT_DIR/.env" \
  --ragflow-url "http://127.0.0.1:9380"

python "$ROOT_DIR/scripts/bootstrap_ragflow_local_models.py" \
  --root-env "$ROOT_DIR/.env" \
  --ragflow-env "$RAGFLOW_DIR/.env"

echo "RAGFlow is reachable at http://localhost:8088 and API port http://localhost:9380"

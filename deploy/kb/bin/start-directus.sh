#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DEPLOY_DIR="$ROOT_DIR/deploy/kb"
ENV_FILE="$DEPLOY_DIR/directus.env"

random_hex() {
  openssl rand -hex 32
}

if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" <<EOF
DIRECTUS_HTTP_PORT=8055
DIRECTUS_PUBLIC_URL=http://localhost:8055
DIRECTUS_DB_NAME=directus
DIRECTUS_DB_USER=directus
DIRECTUS_DB_PASSWORD=$(random_hex)
DIRECTUS_SECRET=$(random_hex)
DIRECTUS_ADMIN_EMAIL=admin@example.com
DIRECTUS_ADMIN_PASSWORD=$(random_hex)
DIRECTUS_ADMIN_TOKEN=luoying-directus-$(random_hex)
EOF
  chmod 600 "$ENV_FILE"
fi

if grep -q '^DIRECTUS_ADMIN_EMAIL=admin@luoying.local$' "$ENV_FILE"; then
  sed -i 's/^DIRECTUS_ADMIN_EMAIL=admin@luoying.local$/DIRECTUS_ADMIN_EMAIL=admin@example.com/' "$ENV_FILE"
fi

docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/compose.directus.yml" up -d

for _ in $(seq 1 90); do
  if curl -fsS http://localhost:8055/server/ping >/dev/null; then
    break
  fi
  sleep 2
done

curl -fsS http://localhost:8055/server/ping >/dev/null

PYTHONPATH="$ROOT_DIR/src" python "$ROOT_DIR/scripts/configure_local_kb_env.py" \
  --env-file "$ROOT_DIR/.env" \
  --directus-url "http://127.0.0.1:8055" \
  --directus-token "$(grep '^DIRECTUS_ADMIN_TOKEN=' "$ENV_FILE" | cut -d= -f2-)" \
  --ragflow-url "http://127.0.0.1:9380"

echo "Directus is ready at http://localhost:8055"

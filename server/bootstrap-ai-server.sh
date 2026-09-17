#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${BASE_DIR:-/opt/pepeuch-ai}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

log() { printf '[PepeuchAI] %s\n' "$*"; }
fail() { printf '[PepeuchAI][ERROR] %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || fail "Run this bootstrap as root."
command -v docker >/dev/null 2>&1 || fail "Docker is not installed."
docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is not installed."

mkdir -p \
  "${BASE_DIR}/postgres" \
  "${BASE_DIR}/ray" \
  "${BASE_DIR}/open-webui" \
  "${BASE_DIR}/qdrant" \
  "${BASE_DIR}/models/ollama" \
  "${BASE_DIR}/logs" \
  "${BASE_DIR}/cache"

if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${SCRIPT_DIR}/.env.example" "${ENV_FILE}"

  POSTGRES_PASSWORD="$(openssl rand -hex 24)"
  WEBUI_SECRET_KEY="$(openssl rand -hex 32)"

  sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=${POSTGRES_PASSWORD}/" "${ENV_FILE}"
  sed -i "s/^WEBUI_SECRET_KEY=.*/WEBUI_SECRET_KEY=${WEBUI_SECRET_KEY}/" "${ENV_FILE}"

  chmod 600 "${ENV_FILE}"
  log "Created .env with generated secrets."
else
  log ".env already exists; leaving it unchanged."
fi

cd "${SCRIPT_DIR}"

log "Validating Compose configuration..."
docker compose --env-file "${ENV_FILE}" config >/dev/null

log "Starting core services: PostgreSQL, Ray Head, Open WebUI..."
docker compose --env-file "${ENV_FILE}" up -d postgres ray-head open-webui

echo
log "Core stack started."
echo
echo "Open WebUI:   http://<AI_VM_IP>:$(grep '^OPEN_WEBUI_PORT=' "${ENV_FILE}" | cut -d= -f2)"
echo "Ray dashboard: http://<AI_VM_IP>:$(grep '^RAY_DASHBOARD_PORT=' "${ENV_FILE}" | cut -d= -f2)"
echo
echo "Optional later:"
echo "  LLM runtime : docker compose --profile llm up -d"
echo "  RAG/Qdrant  : docker compose --profile rag up -d"
echo "  Scheduler   : docker compose --profile scheduler up -d"
echo
echo "Do NOT enable the llm profile until NVIDIA Container Toolkit and GPU passthrough are working."

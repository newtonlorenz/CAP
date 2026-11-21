#!/usr/bin/env sh

set -eu

if [ -n "${CAP_REPO_ROOT:-}" ]; then
  REPO_ROOT=$(CDPATH= cd -- "$CAP_REPO_ROOT" && pwd)
  SCRIPT_DIR="$REPO_ROOT/scripts/deploy"
elif [ -f "$(dirname -- "$0")/common.sh" ]; then
  SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
  REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
else
  REPO_ROOT=$(pwd)
  SCRIPT_DIR="$REPO_ROOT/scripts/deploy"
fi
EDGE_MODE=${CAP_EDGE_MODE:-external}
DEFAULT_COMPOSE_FILE="$REPO_ROOT/docker-compose.prod.yml"
DEFAULT_EDGE_COMPOSE_FILE="$REPO_ROOT/docker-compose.edge.yml"
RAW_COMPOSE_FILE=${COMPOSE_FILE:-}
RAW_COMPOSE_OVERLAYS=${CAP_COMPOSE_OVERLAYS:-}
RAW_ENV_FILE=${CAP_ENV_FILE:-.env.production}
DOCKER_CONTEXT_NAME=${CAP_DOCKER_CONTEXT:-${DOCKER_CONTEXT:-}}

case "$EDGE_MODE" in
  external|bundled) ;;
  *)
    echo "CAP_EDGE_MODE must be one of: external, bundled" >&2
    exit 1
    ;;
esac

resolve_repo_path() {
  case "$1" in
    /*) printf '%s\n' "$1" ;;
    *) printf '%s/%s\n' "$REPO_ROOT" "$1" ;;
  esac
}

resolve_overlay_path() {
  case "$1" in
    structured) printf '%s\n' "$REPO_ROOT/docker-compose.structured.yml" ;;
    ocr) printf '%s\n' "$REPO_ROOT/docker-compose.ocr.yml" ;;
    structured-ocr) printf '%s\n' "$REPO_ROOT/docker-compose.structured-ocr.yml" ;;
    site-content) printf '%s\n' "$REPO_ROOT/docker-compose.site-content.yml" ;;
    edge) printf '%s\n' "$DEFAULT_EDGE_COMPOSE_FILE" ;;
    *) resolve_repo_path "$1" ;;
  esac
}

if [ -n "$RAW_COMPOSE_FILE" ]; then
  COMPOSE_FILE_SOURCE=override
else
  COMPOSE_FILE_SOURCE=default
fi

case "$RAW_ENV_FILE" in
  /*) ENV_FILE=$RAW_ENV_FILE ;;
  *) ENV_FILE="$REPO_ROOT/$RAW_ENV_FILE" ;;
esac

export CAP_ENV_FILE="$ENV_FILE"

compose_file_list() {
  if [ "$COMPOSE_FILE_SOURCE" = "override" ]; then
    old_ifs=$IFS
    IFS=:
    for entry in $RAW_COMPOSE_FILE; do
      if [ -n "$entry" ]; then
        resolve_repo_path "$entry"
      fi
    done
    IFS=$old_ifs
  else
    printf '%s\n' "$DEFAULT_COMPOSE_FILE"
    if [ "$EDGE_MODE" = "bundled" ]; then
      printf '%s\n' "$DEFAULT_EDGE_COMPOSE_FILE"
    fi
  fi

  if [ -n "$RAW_COMPOSE_OVERLAYS" ]; then
    old_ifs=$IFS
    IFS=,
    for overlay in $RAW_COMPOSE_OVERLAYS; do
      if [ -n "$overlay" ]; then
        resolve_overlay_path "$overlay"
      fi
    done
    IFS=$old_ifs
  fi
}

COMPOSE_FILE=$(compose_file_list | head -n 1)

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_file() {
  if [ ! -f "$1" ]; then
    echo "Missing required file: $1" >&2
    exit 1
  fi
}

require_compose_files() {
  for file in $(compose_file_list); do
    require_file "$file"
  done
}

env_value() {
  key=$1
  awk -v key="$key" '
    /^[[:space:]]*#/ { next }
    {
      line = $0
      sub(/^[[:space:]]*export[[:space:]]+/, "", line)
      sub(/^[[:space:]]+/, "", line)
      if (index(line, key "=") != 1) {
        next
      }
      value = substr(line, length(key) + 2)
      sub(/^[[:space:]]+/, "", value)
      if (value ~ /^"/) {
        sub(/^"/, "", value)
        sub(/"[[:space:]]*(#.*)?$/, "", value)
      } else if (value ~ /^\x27/) {
        sub(/^\x27/, "", value)
        sub(/\x27[[:space:]]*(#.*)?$/, "", value)
      } else {
        sub(/[[:space:]]+#.*$/, "", value)
        sub(/[[:space:]]+$/, "", value)
      }
      found = 1
      last = value
    }
    END {
      if (found) {
        print last
      }
    }
  ' "$ENV_FILE"
}

require_nonempty_env() {
  key=$1
  value=$(env_value "$key")
  if [ -z "$value" ]; then
    echo "Missing required environment setting: $key" >&2
    exit 1
  fi
}

docker_cmd() {
  if [ -n "$DOCKER_CONTEXT_NAME" ]; then
    docker --context "$DOCKER_CONTEXT_NAME" "$@"
  else
    docker "$@"
  fi
}

compose() {
  set -- --env-file "$ENV_FILE" "$@"
  files=$(compose_file_list)
  reversed=""
  for file in $files; do
    reversed="$file $reversed"
  done
  for file in $reversed; do
    set -- -f "$file" "$@"
  done
  docker_cmd compose "$@"
}

service_image_id() {
  service=$1
  container_id=$(compose ps -q "$service" 2>/dev/null || true)
  if [ -n "$container_id" ]; then
    docker_cmd inspect --format '{{.Image}}' "$container_id" 2>/dev/null || true
  fi
}

wait_for_service() {
  service=$1
  timeout_seconds=$2
  start_time=$(date +%s)

  while :; do
    container_id=$(compose ps -q "$service")
    if [ -n "$container_id" ]; then
      status=$(docker_cmd inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")
      case "$status" in
        healthy|running)
          return 0
          ;;
        unhealthy|exited|dead)
          echo "Service $service failed with status: $status" >&2
          return 1
          ;;
      esac
    fi

    now=$(date +%s)
    if [ $((now - start_time)) -ge "$timeout_seconds" ]; then
      echo "Timed out waiting for service: $service" >&2
      return 1
    fi

    sleep 2
  done
}

service_defined() {
  service=$1
  compose config --services | awk -v target="$service" '$0 == target { found = 1 } END { exit found ? 0 : 1 }'
}

using_bundled_edge() {
  [ "$COMPOSE_FILE_SOURCE" = "default" ] && [ "$EDGE_MODE" = "bundled" ]
}

retry_curl() {
  url=$1
  timeout_seconds=$2
  start_time=$(date +%s)

  while :; do
    if curl --fail --silent --show-error --location "$url" >/dev/null; then
      return 0
    fi

    now=$(date +%s)
    if [ $((now - start_time)) -ge "$timeout_seconds" ]; then
      echo "Smoke check failed for URL: $url" >&2
      return 1
    fi

    sleep 2
  done
}

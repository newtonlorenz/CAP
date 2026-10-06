#!/usr/bin/env sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
EDGE_MODE=${CAP_EDGE_MODE:-external}
DEFAULT_COMPOSE_FILE="$REPO_ROOT/docker-compose.prod.yml"
DEFAULT_EDGE_COMPOSE_FILE="$REPO_ROOT/docker-compose.edge.yml"
RAW_COMPOSE_FILE=${COMPOSE_FILE:-}
RAW_ENV_FILE=${CAP_ENV_FILE:-.env.production}

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

if [ -n "$RAW_COMPOSE_FILE" ]; then
  COMPOSE_FILE=$(resolve_repo_path "$RAW_COMPOSE_FILE")
  COMPOSE_FILE_SOURCE=override
else
  COMPOSE_FILE=$DEFAULT_COMPOSE_FILE
  COMPOSE_FILE_SOURCE=default
fi

case "$RAW_ENV_FILE" in
  /*) ENV_FILE=$RAW_ENV_FILE ;;
  *) ENV_FILE="$REPO_ROOT/$RAW_ENV_FILE" ;;
esac

export CAP_ENV_FILE="$ENV_FILE"

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
  require_file "$COMPOSE_FILE"
  if [ "$COMPOSE_FILE_SOURCE" = "default" ] && [ "$EDGE_MODE" = "bundled" ]; then
    require_file "$DEFAULT_EDGE_COMPOSE_FILE"
  fi
}

env_value() {
  key=$1
  awk -F= -v key="$key" '
    /^[[:space:]]*#/ { next }
    index($0, key "=") == 1 {
      value = substr($0, length(key) + 2)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      print value
      exit
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

compose() {
  if [ "$COMPOSE_FILE_SOURCE" = "override" ]; then
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
    return
  fi

  if [ "$EDGE_MODE" = "bundled" ]; then
    docker compose -f "$COMPOSE_FILE" -f "$DEFAULT_EDGE_COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
    return
  fi

  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

wait_for_service() {
  service=$1
  timeout_seconds=$2
  start_time=$(date +%s)

  while :; do
    container_id=$(compose ps -q "$service")
    if [ -n "$container_id" ]; then
      status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")
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
      echo "Timed out waiting for URL: $url" >&2
      return 1
    fi

    sleep 3
  done
}

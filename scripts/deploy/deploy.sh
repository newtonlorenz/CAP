#!/usr/bin/env sh

set -eu

. "$(dirname "$0")/common.sh"

DEPLOY_MODE=${CAP_DEPLOY_MODE:-full}
RECEIPT_FILE=${CAP_DEPLOY_RECEIPT_FILE:-"$REPO_ROOT/tmp/deploy-receipt.json"}

while [ $# -gt 0 ]; do
  case "$1" in
    --mode)
      shift
      DEPLOY_MODE=${1:-}
      ;;
    --mode=*)
      DEPLOY_MODE=${1#--mode=}
      ;;
    --context)
      shift
      DOCKER_CONTEXT_NAME=${1:-}
      ;;
    --context=*)
      DOCKER_CONTEXT_NAME=${1#--context=}
      ;;
    *)
      echo "Unknown deploy argument: $1" >&2
      exit 1
      ;;
  esac
  shift
done

case "$DEPLOY_MODE" in
  auto|full|backend|frontend) ;;
  *)
    echo "Deploy mode must be one of: auto, full, backend, frontend" >&2
    exit 1
    ;;
esac

detect_auto_mode() {
  if [ ! -f "$RECEIPT_FILE" ] || ! command -v git >/dev/null 2>&1; then
    printf 'full\n'
    return
  fi
  prev_rev=$(awk -F'"' '/"git_revision":/ { print $4; exit }' "$RECEIPT_FILE" 2>/dev/null || true)
  if [ -z "$prev_rev" ] || ! git -C "$REPO_ROOT" cat-file -e "${prev_rev}^{commit}" 2>/dev/null; then
    printf 'full\n'
    return
  fi
  changed_files=$(
    {
      git -C "$REPO_ROOT" diff --name-only "$prev_rev" 2>/dev/null || true
      git -C "$REPO_ROOT" ls-files --others --exclude-standard 2>/dev/null || true
    } | sed '/^$/d' | sort -u
  )
  if [ -z "$changed_files" ]; then
    printf 'frontend\n'
    return
  fi
  non_frontend=$(printf '%s\n' "$changed_files" | grep -Ev '^(frontend/|README\.md|docs/)' || true)
  if [ -z "$non_frontend" ]; then
    printf 'frontend\n'
    return
  fi
  non_backend=$(printf '%s\n' "$changed_files" | grep -Ev '^(backend/|README\.md|docs/)' || true)
  alembic_changes=$(printf '%s\n' "$changed_files" | grep -E '^backend/alembic/' || true)
  if [ -z "$non_backend" ] && [ -z "$alembic_changes" ]; then
    printf 'backend\n'
    return
  fi
  printf 'full\n'
}

if [ "$DEPLOY_MODE" = "auto" ]; then
  DEPLOY_MODE=$(detect_auto_mode)
  echo "Detected deployment scope: $DEPLOY_MODE"
fi

require_cmd docker
require_compose_files
require_file "$ENV_FILE"

"$SCRIPT_DIR/preflight.sh" --mode "$DEPLOY_MODE"

prev_frontend_image=$(service_image_id frontend)
prev_backend_image=$(service_image_id backend)
prev_celery_image=$(service_image_id celery)
deploy_started_at=$(date +%s)

case "$DEPLOY_MODE" in
  frontend)
    compose up -d --build --no-deps frontend
    check_services="frontend caddy"
    ;;
  backend)
    if service_defined celery; then
      compose up -d --build --no-deps backend celery
    else
      compose up -d --build --no-deps backend
    fi
    check_services="backend celery"
    ;;
  full)
    compose up -d --build
    check_services="db redis backend celery frontend caddy"
    ;;
esac

for service in $check_services; do
  if service_defined "$service"; then
    timeout=120
    if [ "$service" = "backend" ] || [ "$service" = "celery" ]; then
      timeout=180
    fi
    if ! wait_for_service "$service" "$timeout"; then
      if [ "$DEPLOY_MODE" = "frontend" ] && [ -n "$prev_frontend_image" ]; then
        echo "Frontend verification failed; previous image retained: $prev_frontend_image" >&2
      fi
      exit 1
    fi
  fi
done

if [ "$DEPLOY_MODE" != "frontend" ]; then
  compose exec -T backend python -m app.deploy check-http-health >/dev/null
  bootstrap_status=$(compose exec -T backend python -m app.deploy bootstrap-status --deploy-start-epoch "$deploy_started_at")
else
  bootstrap_status="skipped"
fi

public_target=""
if using_bundled_edge; then
  require_cmd curl
  app_domain=$(env_value APP_DOMAIN)
  public_target="https://$app_domain"
  retry_curl "$public_target/" 180
  retry_curl "$public_target/api/v1/health" 180
else
  external_smoke_url=${CAP_EXTERNAL_SMOKE_URL:-}
  external_smoke_url=${external_smoke_url%/}
  if [ -n "$external_smoke_url" ]; then
    require_cmd curl
    public_target=$external_smoke_url
    retry_curl "$public_target/" 180
    retry_curl "$public_target/api/v1/health" 180
  fi
fi

if [ "$DEPLOY_MODE" != "frontend" ]; then
  case "$bootstrap_status" in
    disabled)
      echo "Bootstrap admin is not configured."
      ;;
    ready)
      echo "Bootstrap admin is ready for first login. Sign in with BOOTSTRAP_ADMIN_EMAIL, then clear BOOTSTRAP_ADMIN_* and rotate the temporary password."
      ;;
    already-present)
      echo "Bootstrap admin already existed. If BOOTSTRAP_ADMIN_* is still set, clear it and rotate the temporary password."
      ;;
    missing)
      echo "Bootstrap admin is configured but the user does not exist yet. Check backend logs before continuing." >&2
      exit 1
      ;;
    *)
      echo "Unexpected bootstrap status: $bootstrap_status" >&2
      exit 1
      ;;
  esac
fi

git_revision="unknown"
if command -v git >/dev/null 2>&1; then
  git_revision=$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || printf 'unknown')
fi
curr_frontend_image=$(service_image_id frontend)
curr_backend_image=$(service_image_id backend)
curr_celery_image=$(service_image_id celery)

mkdir -p "$(dirname "$RECEIPT_FILE")"
cat >"$RECEIPT_FILE" <<EOF
{
  "deployed_at_epoch": $deploy_started_at,
  "mode": "$DEPLOY_MODE",
  "git_revision": "$git_revision",
  "images": {
    "frontend": "${curr_frontend_image:-}",
    "backend": "${curr_backend_image:-}",
    "celery": "${curr_celery_image:-}"
  },
  "previous_images": {
    "frontend": "${prev_frontend_image:-}",
    "backend": "${prev_backend_image:-}",
    "celery": "${prev_celery_image:-}"
  }
}
EOF

if [ -n "$public_target" ]; then
  echo "Deployment ($DEPLOY_MODE) completed successfully. Internal checks passed and public smoke checks succeeded for $public_target"
else
  echo "Deployment ($DEPLOY_MODE) completed successfully. Internal checks passed. Public smoke checks were skipped because CAP_EDGE_MODE=external and CAP_EXTERNAL_SMOKE_URL is not set."
fi

#!/usr/bin/env sh

set -eu

. "$(dirname "$0")/common.sh"

require_cmd docker
require_compose_files
require_file "$ENV_FILE"

"$SCRIPT_DIR/preflight.sh"

deploy_started_at=$(date +%s)
compose up -d --build

for service in db redis backend frontend caddy; do
  if service_defined "$service"; then
    timeout=120
    if [ "$service" = "backend" ]; then
      timeout=180
    fi
    wait_for_service "$service" "$timeout"
  fi
done

compose exec -T backend python -m app.deploy check-http-health >/dev/null
bootstrap_status=$(compose exec -T backend python -m app.deploy bootstrap-status --deploy-start-epoch "$deploy_started_at")

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

if [ -n "$public_target" ]; then
  echo "Deployment completed successfully. Internal checks passed and public smoke checks succeeded for $public_target"
else
  echo "Deployment completed successfully. Internal checks passed. Public smoke checks were skipped because CAP_EDGE_MODE=external and CAP_EXTERNAL_SMOKE_URL is not set."
fi

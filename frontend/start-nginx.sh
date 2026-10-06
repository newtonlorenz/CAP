#!/usr/bin/env sh
set -eu

if [ -n "${API_PROXY_TARGET:-}" ]; then
  : # explicit override wins
elif [ -n "${API_PROXY_HOSTPORT:-}" ]; then
  # Render private-network routing (preferred when available).
  API_PROXY_TARGET="${API_PROXY_SCHEME:-http}://${API_PROXY_HOSTPORT}"
else
  API_PROXY_TARGET="${API_PROXY_SCHEME:-http}://${API_PROXY_HOSTPORT_FALLBACK:-cap-backend:10000}"
fi

# Normalize to an origin (scheme://host:port) with no trailing slash or /api suffix.
API_PROXY_TARGET="${API_PROXY_TARGET%/}"
API_PROXY_TARGET="${API_PROXY_TARGET%/api}"
API_PROXY_TARGET="${API_PROXY_TARGET%/}"

API_PROXY_HOST_MODE="${API_PROXY_HOST_MODE:-preserve}"
case "$API_PROXY_HOST_MODE" in
  preserve)
    API_PROXY_HOST_HEADER='$host'
    ;;
  upstream)
    API_PROXY_HOST_HEADER='$proxy_host'
    ;;
  *)
    echo "API_PROXY_HOST_MODE must be one of: preserve, upstream" >&2
    exit 1
    ;;
esac

export API_PROXY_TARGET
export API_PROXY_HOST_HEADER
export FRONTEND_CLIENT_MAX_BODY_SIZE="${FRONTEND_CLIENT_MAX_BODY_SIZE:-2048m}"
export FRONTEND_BASE_PATH="${FRONTEND_BASE_PATH:-/}"
# Restrict the prefix to a single URL segment before placing it in nginx config.
if ! printf '%s' "$FRONTEND_BASE_PATH" | grep -Eq '^/([A-Za-z0-9_-]+/)?$'; then
  echo 'FRONTEND_BASE_PATH must be / or /segment/' >&2
  exit 1
fi
FRONTEND_EXTRA_LOCATIONS=''
if [ "$FRONTEND_BASE_PATH" != / ]; then
  FRONTEND_EXTRA_LOCATIONS="location = / { return 302 ${FRONTEND_BASE_PATH}; }
    location = ${FRONTEND_BASE_PATH%/} { return 308 ${FRONTEND_BASE_PATH}; }
    location / { return 404; }"
fi
export FRONTEND_EXTRA_LOCATIONS

envsubst '${API_PROXY_TARGET} ${API_PROXY_HOST_HEADER} ${FRONTEND_CLIENT_MAX_BODY_SIZE} ${FRONTEND_BASE_PATH} ${FRONTEND_EXTRA_LOCATIONS}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf
exec nginx -g 'daemon off;'

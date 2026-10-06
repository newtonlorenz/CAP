#!/usr/bin/env sh

set -eu

. "$(dirname "$0")/common.sh"

require_cmd docker
require_compose_files
require_file "$ENV_FILE"

require_nonempty_env APP_ENV
require_nonempty_env DB_PASSWORD
require_nonempty_env SECRET_KEY
require_nonempty_env CORS_ORIGINS
require_nonempty_env ALLOWED_HOSTS
require_nonempty_env FRONTEND_BASE_URL
require_nonempty_env AI_PROVIDER
require_nonempty_env EMAIL_MODE

app_env=$(env_value APP_ENV)
if [ "$app_env" != "production" ]; then
  echo "APP_ENV must be set to production in $ENV_FILE" >&2
  exit 1
fi

if using_bundled_edge; then
  require_nonempty_env APP_DOMAIN
fi

ai_provider=$(env_value AI_PROVIDER)
case "$ai_provider" in
  none) ;;
  openai)
    require_nonempty_env OPENAI_API_KEY
    ;;
  anthropic)
    require_nonempty_env ANTHROPIC_API_KEY
    ;;
  auto)
    openai_key=$(env_value OPENAI_API_KEY)
    anthropic_key=$(env_value ANTHROPIC_API_KEY)
    if [ -z "$openai_key" ] && [ -z "$anthropic_key" ]; then
      echo "AI_PROVIDER=auto requires OPENAI_API_KEY or ANTHROPIC_API_KEY." >&2
      exit 1
    fi
    ;;
  *)
    echo "AI_PROVIDER must be one of: none, openai, anthropic, auto" >&2
    exit 1
    ;;
esac

email_mode=$(env_value EMAIL_MODE)
case "$email_mode" in
  disabled) ;;
  smtp)
    require_nonempty_env SMTP_HOST
    require_nonempty_env SMTP_FROM
    smtp_user=$(env_value SMTP_USER)
    smtp_password=$(env_value SMTP_PASSWORD)
    if [ -n "$smtp_user" ] && [ -z "$smtp_password" ]; then
      echo "SMTP_PASSWORD is required when SMTP_USER is set." >&2
      exit 1
    fi
    ;;
  *)
    echo "EMAIL_MODE must be disabled or smtp for production deploys." >&2
    exit 1
    ;;
esac

bootstrap_email=$(env_value BOOTSTRAP_ADMIN_EMAIL)
bootstrap_name=$(env_value BOOTSTRAP_ADMIN_NAME)
bootstrap_password=$(env_value BOOTSTRAP_ADMIN_PASSWORD)
if [ -n "$bootstrap_email" ] || [ -n "$bootstrap_name" ] || [ -n "$bootstrap_password" ]; then
  if [ -z "$bootstrap_email" ] || [ -z "$bootstrap_name" ] || [ -z "$bootstrap_password" ]; then
    echo "BOOTSTRAP_ADMIN_EMAIL, BOOTSTRAP_ADMIN_NAME, and BOOTSTRAP_ADMIN_PASSWORD must all be set together." >&2
    exit 1
  fi
  echo "Warning: BOOTSTRAP_ADMIN_* is set. Treat it as temporary first-deploy access and clear it after the first successful login." >&2
fi

compose config >/dev/null
compose build backend >/dev/null
compose run --rm --no-deps backend python -m app.deploy validate-config >/dev/null

echo "Preflight checks passed for $ENV_FILE"

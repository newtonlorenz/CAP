#!/usr/bin/env sh

set -eu

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

if [ "$(uname -s)" != "Linux" ]; then
  echo "bootstrap-vm.sh currently supports Ubuntu/Debian-style Linux hosts." >&2
  exit 1
fi

if [ -r /etc/os-release ]; then
  . /etc/os-release
  case "${ID:-}" in
    ubuntu|debian) ;;
    *)
      echo "bootstrap-vm.sh expects Ubuntu or Debian. Detected: ${ID:-unknown}" >&2
      exit 1
      ;;
  esac
fi

SUDO=sudo
if [ "$(id -u)" -eq 0 ]; then
  SUDO=
fi

require_cmd apt-get
require_cmd curl

$SUDO apt-get update
$SUDO apt-get install -y ca-certificates curl git

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | $SUDO sh
fi

$SUDO systemctl enable docker >/dev/null 2>&1 || true
$SUDO systemctl start docker >/dev/null 2>&1 || true

user_name=${SUDO_USER:-$(id -un)}
if ! id -nG "$user_name" | grep -qw docker; then
  $SUDO usermod -aG docker "$user_name"
  echo "Added $user_name to the docker group. Log out and back in before running deploy commands."
fi

$SUDO docker --version
$SUDO docker compose version

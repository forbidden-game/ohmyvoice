#!/usr/bin/env bash
# Bootstrap ohmyvoice on macOS from a single command.
# Wrapped in main() so that bash reads the entire script before executing,
# preventing package managers from consuming stdin when run via curl|bash.
set -euo pipefail

main() {

REPO="${OHMYVOICE_GITHUB_REPO:-forbidden-game/ohmyvoice}"
REF="${OHMYVOICE_REF:-main}"
INSTALL_DIR="${OHMYVOICE_INSTALL_DIR:-${HOME}/.local/share/ohmyvoice}"
ARCHIVE_URL="${OHMYVOICE_ARCHIVE_URL:-https://codeload.github.com/${REPO}/tar.gz/refs/heads/${REF}}"
SKIP_PACKAGE_INSTALL="${OHMYVOICE_SKIP_PACKAGE_INSTALL:-0}"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "install-macos.sh only supports macOS." >&2
  exit 1
fi

for cmd in curl tar; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Missing required command: ${cmd}" >&2
    exit 1
  fi
done

activate_homebrew() {
  if command -v brew >/dev/null 2>&1; then
    return
  fi

  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
    return
  fi

  if [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
}

node_major() {
  local node_bin="${1:-}"
  if [ -z "${node_bin}" ] || [ ! -x "${node_bin}" ]; then
    echo 0
    return
  fi

  "${node_bin}" -p "process.versions.node.split('.')[0]"
}

resolve_node_bin() {
  local brew_prefix

  activate_homebrew
  if command -v brew >/dev/null 2>&1; then
    brew_prefix="$(brew --prefix node 2>/dev/null || true)"
    if [ -n "${brew_prefix}" ] && [ -x "${brew_prefix}/bin/node" ]; then
      printf '%s\n' "${brew_prefix}/bin/node"
      return 0
    fi
  fi

  if command -v node >/dev/null 2>&1; then
    command -v node
    return 0
  fi

  return 1
}

ensure_node_runtime() {
  local node_bin
  node_bin="$(resolve_node_bin || true)"

  if [ -z "${node_bin}" ] || [ "$(node_major "${node_bin}")" -lt 20 ]; then
    echo "Node.js 20+ is required, but a compatible runtime was not found." >&2
    echo "Install Homebrew Node or put Node.js 20+ on PATH, then re-run this installer." >&2
    exit 1
  fi

  export OHMYVOICE_NODE_BIN="${node_bin}"
  export PATH="$(dirname "${node_bin}"):${PATH}"
}

ensure_homebrew() {
  activate_homebrew
  if command -v brew >/dev/null 2>&1; then
    return
  fi

  echo "Homebrew not found. Installing Homebrew..."
  NONINTERACTIVE=1 /bin/bash -c \
    "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  activate_homebrew

  if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew installation finished, but brew is still not on PATH." >&2
    echo "Open a new terminal, run 'brew --version', then re-run this installer." >&2
    exit 1
  fi
}

install_dependencies() {
  ensure_homebrew

  echo "[1/3] Installing macOS dependencies..."
  brew install node ffmpeg python3
  brew install --cask hammerspoon
}

download_repo() {
  local tmp_dir archive
  tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/ohmyvoice-install.XXXXXX")"
  archive="${tmp_dir}/ohmyvoice.tar.gz"
  trap 'rm -rf "${tmp_dir}"' EXIT

  echo "[2/3] Downloading ohmyvoice (${REPO}@${REF})..."
  curl -fsSL "${ARCHIVE_URL}" -o "${archive}"
  mkdir -p "$(dirname "${INSTALL_DIR}")"

  if [ -e "${INSTALL_DIR}" ] && [ ! -d "${INSTALL_DIR}" ]; then
    echo "Install path exists but is not a directory: ${INSTALL_DIR}" >&2
    exit 1
  fi

  if [ -d "${INSTALL_DIR}" ]; then
    echo "  Preserving existing files in ${INSTALL_DIR}"
  else
    mkdir -p "${INSTALL_DIR}"
  fi

  tar -xzf "${archive}" --strip-components=1 -C "${INSTALL_DIR}"

  trap - EXIT
  rm -rf "${tmp_dir}"
}

run_setup() {
  echo "[3/3] Running ohmyvoice setup..."
  cd "${INSTALL_DIR}"
  bash ./setup-macos.sh

  if [ -d /Applications/Hammerspoon.app ] || [ -d "${HOME}/Applications/Hammerspoon.app" ]; then
    open -a Hammerspoon >/dev/null 2>&1 || true
  fi
}

if [ "${SKIP_PACKAGE_INSTALL}" != "1" ]; then
  install_dependencies
else
  echo "[1/3] Skipping package installation (OHMYVOICE_SKIP_PACKAGE_INSTALL=1)."
fi

ensure_node_runtime
download_repo
run_setup

echo ""
echo "ohmyvoice is installed in ${INSTALL_DIR}"
echo "Re-run this command anytime to update."

}

main "$@"

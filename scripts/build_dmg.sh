#!/bin/bash
set -euo pipefail

# Thin wrapper around `make dmg`.
# All build/sign/notarize logic lives in the Makefile to avoid duplication.
# Environment variables (DEVELOPER_ID_APPLICATION, NOTARY_PROFILE, etc.)
# are forwarded automatically via Make's ?= defaults.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"

exec make dmg

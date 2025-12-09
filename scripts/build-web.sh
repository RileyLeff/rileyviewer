#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../web"

if command -v bun >/dev/null 2>&1; then
  bun install --silent
  bun run build
elif command -v npm >/dev/null 2>&1; then
  npm install --no-progress
  npm run build
else
  echo "Need bun or npm to build web assets" >&2
  exit 1
fi

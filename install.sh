#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM="claude-code"
ARGS=(--platform "$PLATFORM")
while (($#)); do
  case "$1" in
    --platform) PLATFORM="$2"; ARGS=(--platform "$2"); shift 2 ;;
    --target-root) ARGS+=(--target-root "$2"); shift 2 ;;
    --project|--dry-run|--force|--show-version) ARGS+=("$1"); shift ;;
    -h|--help) echo "Usage: ./install.sh [--platform claude-code|codex|github-copilot] [--project] [--target-root PATH] [--dry-run] [--force] [--show-version]"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done
if [[ ! -d "$ROOT/dist/$PLATFORM" ]]; then
  python3 "$ROOT/scripts/build-distributions.py"
fi
exec python3 "$ROOT/scripts/install.py" "${ARGS[@]}"

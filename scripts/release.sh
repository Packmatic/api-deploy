#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION_FILE="$REPO_ROOT/api_deploy/__init__.py"
BUMP=""

# --- Help ---
usage() {
  cat <<'HELP'
Usage: ./scripts/release.sh [OPTIONS]

Publish packmatic-api-deploy to AWS CodeArtifact. Without options the script
runs interactively.

Options:
  --bump <type>   Version bump type: patch, minor, major, or none
                  (none publishes the version currently in api_deploy/__init__.py)
  --help          Show this help message

Examples:
  ./scripts/release.sh                    # interactive prompts
  ./scripts/release.sh --bump patch       # bump patch, then publish
  ./scripts/release.sh --bump none        # publish the current version as-is

Notes:
  - Run this from develop after your PR is merged.
  - The version is bumped in api_deploy/__init__.py only (no git tags or commits).
    Commit that change yourself afterwards.
  - Requires valid AWS credentials with access to the packmatic CodeArtifact repository.
HELP
  exit 0
}

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --bump) BUMP="$2"; shift 2 ;;
    --help|-h) usage ;;
    *) echo "Unknown option: $1. Use --help for usage."; exit 1 ;;
  esac
done

read_version() {
  python3 -c "import re,sys;print(re.search(r\"VERSION = '([^']+)'\", open(sys.argv[1]).read()).group(1))" "$VERSION_FILE"
}

CURRENT_VERSION="$(read_version)"

# --- Interactive: select bump type ---
if [[ -z "$BUMP" ]]; then
  echo ""
  echo "Current version: $CURRENT_VERSION"
  echo ""
  echo "Version bump type?"
  echo "  1) patch"
  echo "  2) minor"
  echo "  3) major"
  echo "  4) none (publish $CURRENT_VERSION as-is)"
  echo ""
  read -rp "Select [1/2/3/4]: " choice
  case "$choice" in
    1) BUMP="patch" ;;
    2) BUMP="minor" ;;
    3) BUMP="major" ;;
    4) BUMP="none" ;;
    *) echo "Invalid choice"; exit 1 ;;
  esac
fi

if [[ "$BUMP" != "patch" && "$BUMP" != "minor" && "$BUMP" != "major" && "$BUMP" != "none" ]]; then
  echo "Error: Invalid bump type '$BUMP'. Must be 'patch', 'minor', 'major', or 'none'."
  exit 1
fi

# --- Bump version ---
cd "$REPO_ROOT"

if [[ "$BUMP" != "none" ]]; then
  NEW_VERSION=$(BUMP="$BUMP" python3 - "$VERSION_FILE" <<'PY'
import os, re, sys

path = sys.argv[1]
source = open(path).read()
current = re.search(r"VERSION = '([^']+)'", source).group(1)

major, minor, patch = (int(part) for part in current.split('.')[:3])
bump = os.environ['BUMP']
if bump == 'major':
    major, minor, patch = major + 1, 0, 0
elif bump == 'minor':
    minor, patch = minor + 1, 0
else:
    patch += 1

new = f'{major}.{minor}.{patch}'
open(path, 'w').write(re.sub(r"VERSION = '[^']+'", f"VERSION = '{new}'", source))
print(new)
PY
)
  echo "Version bumped to $NEW_VERSION (was $CURRENT_VERSION)"
else
  NEW_VERSION="$CURRENT_VERSION"
  echo "Publishing current version $NEW_VERSION"
fi

# --- Build tooling in a throwaway venv, so nothing global is touched ---
BUILD_VENV="$(mktemp -d)/venv"
trap 'rm -rf "$(dirname "$BUILD_VENV")"' EXIT

echo ""
echo "Preparing build environment..."
python3 -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/pip" install --quiet --upgrade pip build twine

# --- Test ---
echo ""
echo "Running tests..."
"$BUILD_VENV/bin/pip" install --quiet . -r requirements-test.txt
"$BUILD_VENV/bin/python" -m pytest tests/unit -q

# --- Build ---
echo ""
echo "Building distributions..."
rm -rf "$REPO_ROOT/dist"
"$BUILD_VENV/bin/python" -m build --outdir "$REPO_ROOT/dist"
ls -1 "$REPO_ROOT/dist"

# --- Authenticate with CodeArtifact ---
echo ""
echo "Authenticating with AWS CodeArtifact..."
aws codeartifact login \
  --tool twine \
  --domain packmatic \
  --domain-owner 038513119918 \
  --repository packmatic \
  --region eu-central-1

# --- Publish ---
echo ""
echo "Publishing..."
"$BUILD_VENV/bin/twine" upload --repository codeartifact "$REPO_ROOT/dist"/*

# --- Summary ---
echo ""
echo "=========================================="
echo "Release complete!"
echo "=========================================="
echo "  packmatic-api-deploy $NEW_VERSION"
echo ""
echo "  pip install packmatic-api-deploy==$NEW_VERSION"
echo ""
if [[ "$BUMP" != "none" ]]; then
  echo "  Remember to commit the version bump in api_deploy/__init__.py"
  echo ""
fi

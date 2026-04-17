#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UTILITY_TARGET="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/OpenBeat"
UTILITY_SOURCE="$ROOT/resolve/Fusion/Scripts/Utility/OpenBeat"
MODULE_TARGET="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Modules/OpenBeat"
MODULE_SOURCE="$ROOT/resolve/Fusion/Modules/OpenBeat"
CONFIG="$MODULE_SOURCE/OpenBeatConfig.local.lua"
PYTHON_BIN="$ROOT/.venv/bin/python"

mkdir -p "$(dirname "$UTILITY_TARGET")" "$(dirname "$MODULE_TARGET")"
rm -rf "$UTILITY_TARGET" "$MODULE_TARGET"
ln -s "$UTILITY_SOURCE" "$UTILITY_TARGET"
ln -s "$MODULE_SOURCE" "$MODULE_TARGET"

cat > "$CONFIG" <<EOF
return {
  repo_root = "$ROOT",
  python_bin = "$PYTHON_BIN",
}
EOF

echo "Linked OpenBeat Resolve scripts:"
echo "  $UTILITY_TARGET -> $UTILITY_SOURCE"
echo "Linked OpenBeat Resolve modules:"
echo "  $MODULE_TARGET -> $MODULE_SOURCE"
echo "Wrote OpenBeat config:"
echo "  $CONFIG"

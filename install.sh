#!/usr/bin/env bash
# Install the standalone `routism` CLI/TUI on PATH (no pip required).
# This package does NOT ship the product stack; first setup clones Dreamstick9/Routism.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DEST_DIR="${HOME}/.local/bin"
DEST="$DEST_DIR/routism"

mkdir -p "$DEST_DIR"
cat > "$DEST" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="${ROOT}\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m routism_cli "\$@"
EOF
chmod +x "$DEST"
chmod +x "$ROOT/bin/routism" 2>/dev/null || true

echo "Installed: $DEST"
echo "  (standalone routism-cli → operates product from GitHub)"
echo
if ! echo ":$PATH:" | grep -q ":$DEST_DIR:"; then
  echo "Add to your PATH (zsh):"
  echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc && source ~/.zshrc"
  echo
fi
echo "Then:"
echo "  routism install     # clone https://github.com/Dreamstick9/Routism → ~/Routism"
echo "  routism setup -y    # Docker + Ollama + engine models + compose up"
echo "  routism tui         # terminal menu UI"
echo
echo "Optional: export ROUTISM_HOME=/path/to/Routism"

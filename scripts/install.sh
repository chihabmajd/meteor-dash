#!/usr/bin/env bash
# meteor-dash installer — sets up config, the optional mpv hook, and (optionally)
# a launcher + desktop entry. Safe to re-run.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CFGDIR="${XDG_CONFIG_HOME:-$HOME/.config}"

echo "meteor-dash @ $REPO"

# 1. config
if [[ ! -f "$REPO/config.toml" ]]; then
  cp "$REPO/config.example.toml" "$REPO/config.toml"
  echo "  created config.toml (edit it, or see docs/CONFIGURE.md)"
else
  echo "  config.toml exists — leaving it"
fi

# 2. state dir
mkdir -p "$CFGDIR/meteor-dash"
touch "$CFGDIR/meteor-dash/watched.txt"

# 3. optional mpv history hook
read -rp "  install mpv watch-history hook? [y/N] " a
if [[ "${a:-n}" =~ ^[Yy]$ ]]; then
  mkdir -p "$CFGDIR/mpv/scripts"
  cp "$REPO/scripts/mpv-history.lua" "$CFGDIR/mpv/scripts/mpv-history.lua"
  echo "  installed mpv hook -> $CFGDIR/mpv/scripts/"
fi

# 4. launcher on PATH
BIN="$HOME/.local/bin"
mkdir -p "$BIN"
cat > "$BIN/meteor-dash" <<EOF
#!/usr/bin/env bash
cd "$REPO" && exec python3 -m meteordash "\$@"
EOF
chmod +x "$BIN/meteor-dash"
echo "  launcher -> $BIN/meteor-dash  (ensure ~/.local/bin is on PATH)"

echo "done. run:  meteor-dash    then open http://localhost:8777"

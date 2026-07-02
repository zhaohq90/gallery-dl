#!/bin/bash
# One-click start for the user config editor web server
# Usage: ./start_editor.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Detect Python
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "Error: Python not found. Please install Python 3."
    exit 1
fi

# Auto-open browser only on desktop environments (skip on headless/VPS)
if [ "$(uname)" = "Darwin" ]; then
    (sleep 1 && open http://localhost:8899) &
elif [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ]; then
    if command -v xdg-open &>/dev/null; then
        (sleep 1 && xdg-open http://localhost:8899) &
    fi
else
    echo "  (无桌面环境，跳过自动打开浏览器)"
fi

exec "$PYTHON" user_editor.py

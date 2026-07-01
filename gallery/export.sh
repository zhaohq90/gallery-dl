#!/usr/bin/env bash
#
# export.sh — 启动批量导出工具
#
# 自动激活虚拟环境并运行 export.py，退出时还原 shell 环境。
#
# 用法:
#     ./export.sh
#
# 首次使用前:
#     python3 -m venv .venv
#     source .venv/bin/activate
#     pip install gallery-dl
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

if [[ ! -d "${VENV_DIR}" ]]; then
    echo "错误: 虚拟环境不存在 — ${VENV_DIR}"
    echo ""
    echo "请先创建虚拟环境:"
    echo "  cd '${SCRIPT_DIR}'"
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install gallery-dl"
    exit 1
fi

# 激活虚拟环境
# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

# 运行导出脚本
cd "${SCRIPT_DIR}"
python export.py "$@"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
PYTHON_BIN="${PYTHON_BIN:-}"

cd "$ROOT_DIR"

if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if VER="$("$candidate" -c 'import sys; print("{}.{}".format(sys.version_info.major, sys.version_info.minor))' 2>/dev/null)"; then
        MAJOR="${VER%%.*}"
        MINOR="${VER##*.}"
        if [[ "$MAJOR" -gt 3 || ("$MAJOR" -eq 3 && "$MINOR" -ge 10) ]]; then
          PYTHON_BIN="$candidate"
          break
        fi
      fi
    fi
  done
fi

if [[ -z "$PYTHON_BIN" ]] || ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "[ERROR] 未找到 Python 3.10+ 可执行文件。请安装后重试，或通过 PYTHON_BIN 指定。"
  exit 1
fi

echo "[INFO] 使用 Python: $PYTHON_BIN ($($PYTHON_BIN --version 2>&1))"

if [[ -d "$VENV_DIR" ]]; then
  if [[ -x "$VENV_DIR/Scripts/python.exe" ]]; then
    VENV_PY="$VENV_DIR/Scripts/python.exe"
    VENV_VER="$($VENV_PY -c 'import sys; print("{}.{}".format(sys.version_info.major, sys.version_info.minor))')"
    VENV_MAJOR="${VENV_VER%%.*}"
    VENV_MINOR="${VENV_VER##*.}"
    if [[ "$VENV_MAJOR" -lt 3 || ("$VENV_MAJOR" -eq 3 && "$VENV_MINOR" -lt 10) ]]; then
      echo "[INFO] 现有 .venv Python 版本为 ${VENV_VER}，低于 3.10，重建虚拟环境"
      rm -rf "$VENV_DIR"
    fi
  elif [[ -x "$VENV_DIR/bin/python" ]]; then
    VENV_PY="$VENV_DIR/bin/python"
    VENV_VER="$($VENV_PY -c 'import sys; print("{}.{}".format(sys.version_info.major, sys.version_info.minor))')"
    VENV_MAJOR="${VENV_VER%%.*}"
    VENV_MINOR="${VENV_VER##*.}"
    if [[ "$VENV_MAJOR" -lt 3 || ("$VENV_MAJOR" -eq 3 && "$VENV_MINOR" -lt 10) ]]; then
      echo "[INFO] 现有 .venv Python 版本为 ${VENV_VER}，低于 3.10，重建虚拟环境"
      rm -rf "$VENV_DIR"
    fi
  else
    echo "[INFO] 现有 .venv 不完整，重建虚拟环境"
    rm -rf "$VENV_DIR"
  fi
fi

if [[ ! -d "$VENV_DIR" ]]; then
  echo "[INFO] 创建虚拟环境: $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

if [[ -x "$VENV_DIR/Scripts/python.exe" ]]; then
  VENV_PY="$VENV_DIR/Scripts/python.exe"
elif [[ -x "$VENV_DIR/bin/python" ]]; then
  VENV_PY="$VENV_DIR/bin/python"
else
  echo "[ERROR] 虚拟环境创建成功但未找到 Python 可执行文件"
  exit 1
fi

echo "[INFO] 升级 pip"
"$VENV_PY" -m pip install --upgrade pip >/dev/null

echo "[INFO] 安装依赖: backend/requirements.txt"
"$VENV_PY" -m pip install -r backend/requirements.txt

echo "[OK] 依赖安装完成"

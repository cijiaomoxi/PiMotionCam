#!/usr/bin/env bash
# 编译 PiMotionCam 原生加速内核（core/_libpkc.so）
#
# 编译失败不影响服务运行 —— core/native.py 会自动回落到纯 Python + numpy 实现。
#
# 用法：
#   bash build_native.sh              # 在当前目录（版本目录）编译
#   bash build_native.sh --force      # 强制重新编译
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 若脚本位于 core/ 下，则上一级才是包根
[ -f "$HERE/core/_pkc_native.c" ] || HERE="$(dirname "$HERE")"

SRC="$HERE/core/_pkc_native.c"
LIB="$HERE/core/_libpkc.so"
CC="${PKC_CC:-gcc}"
FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

if [ ! -f "$SRC" ]; then
  echo "找不到源文件: $SRC" >&2
  exit 1
fi

if ! command -v "$CC" >/dev/null 2>&1; then
  echo "找不到编译器: $CC（将回落到纯 Python 实现）" >&2
  exit 1
fi

# JPEG 编码需要 libjpeg-turbo 开发包
if ! [ -f /usr/include/jpeglib.h ]; then
  echo "==> 安装 libjpeg62-turbo-dev"
  sudo apt-get install -y -qq libjpeg62-turbo-dev || {
    echo "安装失败，将回落到纯 Python 实现" >&2
    exit 1
  }
fi

# 用数组传编译参数：未加引号的变量展开会被 shell 二次解析，
# 宏里的 \" 会被吃掉，导致 "missing terminating \" character"。
CFLAGS=(-O3 -fPIC -shared -fno-strict-aliasing)
# aarch64 显式打开 NEON；其它架构用编译器默认
case "$(uname -m)" in
  aarch64|arm64) CFLAGS+=(-march=armv8-a+simd) ;;
esac

# 版本号与 core/__init__.py 保持一致（避免发布新版本后日志里还显示旧版本）
PKC_VERSION="$(grep -oE '__version__\s*=\s*"[^"]+"' "$HERE/core/__init__.py" 2>/dev/null \
  | head -1 | sed -E 's/.*"([^"]+)".*/\1/')"
[ -n "$PKC_VERSION" ] || PKC_VERSION="unknown"
CFLAGS+=("-DPKC_VERSION_STR=\"PiMotionCam native ${PKC_VERSION}\"")

echo "==> 编译 $(basename "$SRC")"
if [ "$FORCE" = "1" ]; then
  rm -f "$LIB"
fi

# shellcheck disable=SC2086
if "$CC" "${CFLAGS[@]}" -o "$LIB" "$SRC" -ljpeg -lm 2>/tmp/pkc_build.log; then
  SIZE=$(stat -c %s "$LIB" 2>/dev/null || echo "?")
  echo "编译成功: $LIB (${SIZE} 字节)"
  exit 0
fi

echo "编译失败，日志：" >&2
cat /tmp/pkc_build.log >&2
echo "服务将以纯 Python 实现运行（功能不受影响，仅性能较低）" >&2
exit 1

#!/usr/bin/env bash
# 发布一个新版本到树莓派。
#
# 设计原则：**每个版本都保留，绝不覆盖**。
#   ~/pikrellcam-lite/releases/<时间戳>-v<版本>/   每个版本一个独立目录
#   ~/pikrellcam-lite/current -> releases/<...>       软链指向当前运行版本
#   ~/pikrellcam-lite/{media,logs,venv,config.json}  各版本共享
#
# 回滚：ln -sfn releases/<旧版本> ~/pikrellcam-lite/current && systemctl --user restart pikrellcam-lite
#
# 用法：
#   bash deploy.sh                 # 发布当前工作目录
#   bash deploy.sh --rollback v2.0.0
#   bash deploy.sh --list
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${PKC_HOST:-pi@pi.local}"
KEY="${PKC_KEY:-$HOME/.ssh/id_ed25519_pi_mcode}"
SSH=(ssh -i "$KEY" -o BatchMode=yes "$HOST")
REMOTE_ROOT='$HOME/pikrellcam-lite'   # 保持字面量，由远端 shell 展开 $HOME

die() { echo "错误: $*" >&2; exit 1; }

read_version() {
  grep -oE '__version__\s*=\s*"[^"]+"' "$HERE/core/__init__.py" 2>/dev/null \
    | head -1 | sed -E 's/.*"([^"]+)".*/\1/' || echo "0.0.0"
}

case "${1:-publish}" in
  --list)
    "${SSH[@]}" "ls -1 $REMOTE_ROOT/releases 2>/dev/null | sort"
    echo "当前运行: $( "${SSH[@]}" "readlink $REMOTE_ROOT/current 2>/dev/null || echo 无" )"
    exit 0
    ;;
  --rollback)
    target="${2:-}"
    [ -n "$target" ] || die "用法: bash deploy.sh --rollback <版本号>"
    "${SSH[@]}" "set -e; d=\$(ls -1 $REMOTE_ROOT/releases | grep -- '$target' | tail -1); \
      [ -n \"\$d\" ] || { echo '找不到该版本' >&2; exit 1; }; \
      ln -sfn 'releases/'\"\$d\" $REMOTE_ROOT/current; \
      systemctl --user restart pikrellcam-lite.service; echo \"已回滚到 \$d\""
    exit 0
    ;;
  publish|"") ;;
  *) die "未知参数: $1" ;;
esac

VERSION="$(read_version)"
RELEASE="$(date +%Y%m%d-%H%M)-v${VERSION}"

# 防覆盖：发布目录名只精确到分钟，同一分钟内再次发布会覆盖已有版本目录，
# 违反"每个版本独立保留、绝不覆盖"的约束。这里自动加 -r2 / -r3 后缀。
if "${SSH[@]}" "test -d $REMOTE_ROOT/releases/${RELEASE}"; then
  N=2
  while "${SSH[@]}" "test -d $REMOTE_ROOT/releases/${RELEASE}-r${N}"; do
    N=$((N+1))
    [ "$N" -gt 99 ] && die "同名版本过多，请先清理 releases/"
  done
  echo "==> 已有同名发布目录，自动改用 ${RELEASE}-r${N}（不覆盖历史版本）"
  RELEASE="${RELEASE}-r${N}"
fi

echo "==> 打包 v${VERSION}"
TARBALL="$(mktemp -t pkc-release)"
trap 'rm -f "$TARBALL"' EXIT
tar czf "$TARBALL" \
  --exclude='./versions' \
  --exclude='./dist' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='./deploy.sh' \
  -C "$HERE" .

echo "==> 上传到 releases/${RELEASE}"
"${SSH[@]}" "mkdir -p $REMOTE_ROOT/releases/${RELEASE}"
"${SSH[@]}" "tar xzf - -C $REMOTE_ROOT/releases/${RELEASE}" < "$TARBALL"

echo "==> 更新 systemd 单元（让 ffmpeg 有机会正常收尾）"
"${SSH[@]}" 'set -e
U="$HOME/.config/systemd/user/pikrellcam-lite.service"
mkdir -p "$(dirname "$U")"
touch "$U"
if ! grep -q "^KillMode=mixed" "$U"; then
  if grep -q "^RestartSec=" "$U"; then
    sed -i "/^RestartSec=/a KillMode=mixed\nTimeoutStopSec=30" "$U"
  else
    printf "\nKillMode=mixed\nTimeoutStopSec=30\n" >> "$U"
  fi
  echo "已写入 KillMode=mixed / TimeoutStopSec=30"
else
  echo "systemd 单元已是最新"
fi
systemctl --user daemon-reload'

echo "==> 切换 current 并重启"
"${SSH[@]}" "set -e; \
  ln -sfn 'releases/${RELEASE}' $REMOTE_ROOT/current; \
  systemctl --user daemon-reload; \
  systemctl --user restart pikrellcam-lite.service; \
  sleep 3; \
  echo '当前运行:'; readlink $REMOTE_ROOT/current; \
  echo '已保留的版本:'; ls -1 $REMOTE_ROOT/releases | sort; \
  echo '服务状态:'; systemctl --user is-active pikrellcam-lite.service"

echo "==> 编译原生加速内核"
"${SSH[@]}" "bash $REMOTE_ROOT/current/build_native.sh --force" || \
  echo "（原生内核编译失败，服务自动回落到纯 Python 实现）"
"${SSH[@]}" "systemctl --user restart pikrellcam-lite.service; sleep 3; \
  echo '服务状态:'; systemctl --user is-active pikrellcam-lite.service; \
  echo '加速后端:'; $REMOTE_ROOT/venv/bin/python -c \"import sys;sys.path.insert(0,'$REMOTE_ROOT/current');from core import native;print(native.backend())\""

echo
echo "发布完成: v${VERSION} (${RELEASE})"
echo "历史版本全部保留在 $REMOTE_ROOT/releases/ 下"

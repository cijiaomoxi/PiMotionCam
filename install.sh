#!/usr/bin/env bash
# PiMotionCam 安装脚本（在树莓派上以 pi 用户运行）
#
# 目录结构（每个版本独立保留，互不覆盖）：
#   ~/pikrellcam-lite/
#   ├── current -> releases/<时间戳>-v<版本>/    当前运行版本（软链）
#   ├── releases/<...>/                        所有历史版本
#   ├── media/ logs/ venv/ config.json          各版本共享
#
# 用法：bash ~/pikrellcam-lite/install.sh
set -euo pipefail

ROOT="$HOME/pikrellcam-lite"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIP_INDEX="https://mirrors.aliyun.com/pypi/simple/"

# 当前脚本可能在 releases/<id>/ 里，先定位到根目录
if [ "$(basename "$(dirname "$SRC")")" = "releases" ]; then
  ROOT="$(dirname "$(dirname "$SRC")")"
fi

VERSION=$(grep -oE '__version__\s*=\s*"[^"]+"' "$SRC/core/__init__.py" 2>/dev/null \
  | head -1 | sed -E 's/.*"([^"]+)".*/\1/' || echo "0.0.0")
RELEASE="$(date +%Y%m%d-%H%M)-v${VERSION}"

mkdir -p "$ROOT/releases" "$ROOT/media/videos" "$ROOT/media/stills" "$ROOT/media/timelapse" \
         "$ROOT/logs" "$HOME/.pikrellcam"
chmod 700 "$HOME/.pikrellcam"

# ---------------------------------------------------------------- 系统依赖
need_apt=0
for pkg in python3-venv python3-picamera2 python3-numpy python3-pil ffmpeg; do
  dpkg -s "$pkg" >/dev/null 2>&1 || { echo "缺少系统包: $pkg"; need_apt=1; }
done
if [ "$need_apt" = "1" ]; then
  echo "==> 安装系统依赖（apt）"
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv python3-picamera2 python3-numpy python3-pil ffmpeg
fi

# ---------------------------------------------------------------- 虚拟环境
echo "==> 创建虚拟环境（继承系统包以便使用 picamera2 / numpy / PIL）"
[ -d "$ROOT/venv" ] || python3 -m venv --system-site-packages "$ROOT/venv"

echo "==> 安装 Python 依赖"
"$ROOT/venv/bin/pip" install --disable-pip-version-check -q --upgrade pip -i "$PIP_INDEX" || true
"$ROOT/venv/bin/pip" install --disable-pip-version-check -q flask -i "$PIP_INDEX"

# ---------------------------------------------------------------- 发布目录
TARGET="$ROOT/releases/$RELEASE"
if [ "$SRC" != "$TARGET" ]; then
  echo "==> 安装到版本目录 releases/$RELEASE"
  mkdir -p "$TARGET"
  cp -a "$SRC"/. "$TARGET"/ 2>/dev/null || true
  rm -rf "$TARGET/releases"
fi

# 首次安装时补一份默认配置
[ -f "$ROOT/config.json" ] || cp -a "$TARGET/config.json" "$ROOT/config.json" 2>/dev/null || true

# ---------------------------------------------------------------- systemd
echo "==> 安装 systemd user service"
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/pikrellcam-lite.service" <<EOF
[Unit]
Description=PiMotionCam camera monitoring and recording
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$ROOT/current
ExecStart=$ROOT/venv/bin/python $ROOT/current/pimotioncam.py
Restart=always
RestartSec=5
# KillMode=mixed：SIGTERM 只发给主进程，ffmpeg 子进程由主进程负责收尾。
# 默认的 control-group 会连 ffmpeg 一起杀，而 ffmpeg 阻塞在读 stdin 时
# 任何信号都不会让它写出 moov atom，结果是每次重启都留下一个打不开的 mp4。
KillMode=mixed
# 给 ffmpeg 写 moov 留出时间（正常 1~2 秒即可）
TimeoutStopSec=30
Environment=LANG=zh_CN.UTF-8
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

ln -sfn "releases/$RELEASE" "$ROOT/current"
systemctl --user daemon-reload
systemctl --user enable --now pikrellcam-lite.service

# ---------------------------------------------------------------- 原生加速内核
echo "==> 编译原生加速内核（失败则自动回落纯 Python 实现）"
bash "$ROOT/current/build_native.sh" --force || true
systemctl --user restart pikrellcam-lite.service

echo "==> 开启 linger（无图形登录会话时也能开机自启）"
sudo loginctl enable-linger "$USER" || echo "linger 设置失败，可稍后手动重试"

sleep 4
echo
echo "==> 当前运行版本: $(readlink "$ROOT/current")"
echo "==> 已保留的版本:"
ls -1 "$ROOT/releases" | sed 's/^/    /'
echo
echo "==> 服务状态"
systemctl --user --no-pager --lines=10 status pikrellcam-lite.service || true
PORT=$(python3 -c "import json;print(json.load(open('$ROOT/config.json'))['web']['port'])" 2>/dev/null || echo 8080)
echo
echo "==> 访问地址: http://$(hostname):${PORT}/"

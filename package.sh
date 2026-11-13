#!/usr/bin/env bash
# 打包 pikrellcam-lite，产出可用于 GitHub Release 的发布包。
#
# 产出物（默认落在 dist/）：
#   pikrellcam-lite-v<版本>-<日期>.tar.gz   完整源码包
#   pikrellcam-lite-v<版本>-<日期>.tar.gz.sha256   校验和
#   pikrellcam-lite-v<版本>-<日期>.zip             同内容（给 Windows 用户）
#
# 设计原则：
#   * 打包内容 = 干净仓库（不含本地版本快照、缓存、录像、日志、虚拟环境）；
#   * 打包后自动校验关键文件齐全、版本号一致、两个语言包键集合一致；
#   * 校验不通过直接失败，不产出坏包。
#
# 用法：
#   bash package.sh              # 打包当前版本
#   bash package.sh --out /tmp   # 指定输出目录
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="$HERE/dist"
DO_ZIP=1

for arg in "$@"; do
  case "$arg" in
    --out=*) OUT_DIR="${arg#--out=}" ;;
    --out)   shift; OUT_DIR="${1:-}" ;;
    --no-zip) DO_ZIP=0 ;;
    -h|--help)
      sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "未知参数: $arg" >&2; exit 1 ;;
  esac
done

die() { echo "错误: $*" >&2; exit 1; }

read_version() {
  grep -oE '__version__\s*=\s*"[^"]+"' "$HERE/core/__init__.py" 2>/dev/null \
    | head -1 | sed -E 's/.*"([^"]+)".*/\1/' || echo "0.0.0"
}

VERSION="$(read_version)"
[ "$VERSION" != "0.0.0" ] || die "读不到版本号，检查 core/__init__.py"
DATE="$(date +%Y%m%d)"
BASE="pikrellcam-lite-v${VERSION}-${DATE}"

echo "==> 打包 pikrellcam-lite v${VERSION}"

# ----------------------------------------------------------------------
# 1. 收集文件
# ----------------------------------------------------------------------
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
PKGDIR="$STAGE/pikrellcam-lite"
mkdir -p "$PKGDIR"

copy() {   # copy <相对路径>
  local rel="$1"
  [ -e "$HERE/$rel" ] || { echo "    缺少 $rel，跳过"; return 0; }
  mkdir -p "$PKGDIR/$(dirname "$rel")"
  cp -R "$HERE/$rel" "$PKGDIR/$rel"
}

echo "==> 收集文件"
copy core
copy templates
copy static
copy docs
copy tools
copy install.sh
copy deploy.sh
copy build_native.sh
copy krellcam.py
copy config.json
copy README.md
copy README.en.md
copy CHANGELOG.md
copy LICENSE

# 打包配置示例（去掉本机密码哈希与个人路径）
if [ -f "$PKGDIR/config.json" ]; then
  python3 - "$PKGDIR/config.json" <<'PY'
import json, sys
p = sys.argv[1]
try:
    data = json.load(open(p, encoding="utf-8"))
except Exception:
    sys.exit(0)
web = data.get("web")
if isinstance(web, dict):
    web.pop("password_hash", None)
json.dump(data, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
open(p, "a", encoding="utf-8").write("\n")
PY
fi

# ----------------------------------------------------------------------
# 2. 清理不该进包的东西
# ----------------------------------------------------------------------
echo "==> 清理"
find "$PKGDIR" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$PKGDIR" -name '*.pyc' -type f -delete 2>/dev/null || true
find "$PKGDIR" -name '.DS_Store' -type f -delete 2>/dev/null || true
rm -rf "$PKGDIR/versions" "$PKGDIR/media" "$PKGDIR/logs" "$PKGDIR/venv" 2>/dev/null || true
chmod +x "$PKGDIR/install.sh" "$PKGDIR/build_native.sh" "$PKGDIR/krellcam.py" \
       "$PKGDIR/deploy.sh" 2>/dev/null || true

# ----------------------------------------------------------------------
# 3. 校验
# ----------------------------------------------------------------------
echo "==> 校验"
REQUIRED=(
  "core/__init__.py" "core/app.py" "core/camera.py" "core/config.py"
  "core/detect.py" "core/hooks.py" "core/i18n.py" "core/imaging.py"
  "core/native.py" "core/presets.py" "core/recorder.py" "core/scheduler.py"
  "core/servo.py" "core/state.py" "core/storage.py" "core/timelapse.py"
  "core/util.py" "core/web.py"
  "core/_pkc_native.c"
  "core/locales/zh-CN.json" "core/locales/en-US.json"
  "templates/index.html" "templates/login.html"
  "static/app.js" "static/i18n.js" "static/style.css"
  "docs/使用文档.md" "docs/USAGE.en.md" "docs/上游功能对照.md"
  "README.md" "README.en.md" "CHANGELOG.md" "LICENSE"
  "install.sh" "build_native.sh" "krellcam.py" "deploy.sh"
  "tools/test_v270.py"
)
MISSING=0
for rel in "${REQUIRED[@]}"; do
  if [ ! -f "$PKGDIR/$rel" ]; then
    echo "    ✗ 缺少 $rel"
    MISSING=$((MISSING+1))
  fi
done
[ "$MISSING" -eq 0 ] || die "发布包缺少 $MISSING 个必需文件"

# 版本号一致
PKG_VER="$(grep -oE '__version__\s*=\s*"[^"]+"' "$PKGDIR/core/__init__.py" \
  | head -1 | sed -E 's/.*"([^"]+)".*/\1/')"
[ "$PKG_VER" = "$VERSION" ] || die "包内版本号($PKG_VER) 与脚本读到的不一致($VERSION)"

# 两个语言包键集合必须一致，且不能有空文案
python3 - "$PKGDIR/core/locales" <<'PY'
import json, sys, pathlib
d = pathlib.Path(sys.argv[1])
packs = {}
for code in ("zh-CN", "en-US"):
    f = d / ("%s.json" % code)
    if not f.is_file():
        raise SystemExit("缺少语言包: %s" % f)
    packs[code] = json.loads(f.read_text(encoding="utf-8"))
    empty = [k for k, v in packs[code].items() if not str(v).strip()]
    if empty:
        raise SystemExit("%s 有 %d 条空文案: %s" % (code, len(empty), empty[:5]))
ka, kb = set(packs["zh-CN"]), set(packs["en-US"])
if ka != kb:
    raise SystemExit("两个语言包键集合不一致，仅 zh 多: %s，仅 en 多: %s"
                     % (sorted(ka - kb)[:5], sorted(kb - ka)[:5]))
same = [k for k in ka if packs["zh-CN"][k] == packs["en-US"][k] and len(str(packs["zh-CN"][k])) > 1]
if same:
    print("    ⚠ %d 条中英文案完全相同（通常是术语/proper noun，可接受）: %s"
          % (len(same), sorted(same)[:6]))
print("    语言包校验通过：%d 条文案，中英键集合一致" % len(ka))
PY

# 前端不得残留未翻译的中文（静态文案已在 data-i18n 标记内，检查标记覆盖率）
python3 - "$PKGDIR" <<'PY'
import re, sys, pathlib
root = pathlib.Path(sys.argv[1])
CJK = re.compile(r"[　-鿿＀-￯]")
for rel in ("templates/index.html", "templates/login.html"):
    src = (root / rel).read_text(encoding="utf-8")
    body = re.sub(r"<script\b[^>]*>.*?</script>", "", src, flags=re.S)
    # 去掉已打 data-i18n 标记的片段，剩下的可见中文才算漏网
    marked = re.sub(r'<[^>]*data-i18n[^>]*>.*?</[^>]+>', "", body, flags=re.S)
    marked = re.sub(r"data-i18n[^=]*=\"[^\"]*\"", "", marked)
    leftovers = [t.strip() for t in re.findall(r">([^<>]+)<", marked) if CJK.search(t)]
    if leftovers:
        raise SystemExit("%s 仍有未标记的中文: %s" % (rel, leftovers[:5]))
print("    模板标记校验通过：静态文案均已带 data-i18n")
PY

# ----------------------------------------------------------------------
# 4. 生成发布包
# ----------------------------------------------------------------------
mkdir -p "$OUT_DIR"
TARBALL="$OUT_DIR/$BASE.tar.gz"
ZIP="$OUT_DIR/$BASE.zip"

echo "==> 生成 tar.gz"
tar czf "$TARBALL" -C "$STAGE" pikrellcam-lite

if [ "$DO_ZIP" = "1" ] && command -v zip >/dev/null 2>&1; then
  echo "==> 生成 zip"
  (cd "$STAGE" && zip -qr "$OUT_DIR/$BASE.zip" pikrellcam-lite)
fi

# ----------------------------------------------------------------------
# 4.5 解包自检：把刚打好的包解开，跑一遍语法检查
# ----------------------------------------------------------------------
echo "==> 解包自检"
CHECKDIR="$(mktemp -d)"
tar xzf "$TARBALL" -C "$CHECKDIR"
PKGDIR="$CHECKDIR/pikrellcam-lite"

python3 -m compileall -q "$PKGDIR/core" "$PKGDIR/tools" >/dev/null 2>&1 || true
if command -v node >/dev/null 2>&1; then
  for js in "$PKGDIR/static/app.js" "$PKGDIR/static/i18n.js"; do
    node --check "$js" || die "解包后 JS 语法校验失败: $js"
  done
  echo "    JS 语法校验通过"
fi
python3 - "$PKGDIR" <<'PY2'
import ast, pathlib, sys
root = pathlib.Path(sys.argv[1])
bad = []
for p in sorted(root.glob("core/*.py")) + sorted(root.glob("tools/*.py")):
    try:
        ast.parse(p.read_text(encoding="utf-8"))
    except SyntaxError as e:
        bad.append("%s: %s" % (p.name, e))
if bad:
    raise SystemExit("解包后 Python 语法校验失败:\n  " + "\n  ".join(bad))
print("    Python 语法校验通过")
PY2
rm -rf "$CHECKDIR"

echo "==> 生成校验和"
( cd "$OUT_DIR" && shasum -a 256 "$(basename "$TARBALL")" > "$(basename "$TARBALL").sha256" )

SIZE="$(du -h "$TARBALL" | cut -f1)"
COUNT="$(tar tzf "$TARBALL" | wc -l | tr -d ' ')"

echo
echo "打包完成：v${VERSION}"
echo "  $TARBALL  ($SIZE, $COUNT 个条目)"
[ "$DO_ZIP" = "1" ] && [ -f "$ZIP" ] && echo "  $ZIP"
echo "  $TARBALL.sha256"
echo
echo "发布到 GitHub："
echo "  gh release create v${VERSION} \\"
echo "    \"$TARBALL\" \"$TARBALL.sha256\" \\"
echo "    --title \"v${VERSION}\" --notes-file CHANGELOG.md"

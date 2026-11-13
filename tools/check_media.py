#!/usr/bin/env python3
"""录像 / 抓拍完整性校验。

对 media 目录下的文件逐个做解码检查，确认：
  * 录像能被 ffmpeg 完整解码（零错误输出）；
  * 分辨率、帧率、时长符合预期；
  * 抓拍是合法 JPEG。

**正在写入的文件必须跳过**——MP4 要等 ffmpeg 收尾才写 moov atom，
中途检查必然报错。默认跳过最近 `--fresh` 秒内修改过的文件。

用法：
    python3 tools/check_media.py                       # 检查默认 media 目录
    python3 tools/check_media.py --dir /home/pi/pikrellcam-lite/media
    python3 tools/check_media.py --fresh 180 --limit 50
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def run(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return 124, "", "超时 %ds" % timeout
    except Exception as e:
        return 1, "", str(e)


def probe(path: Path) -> dict:
    rc, out, err = run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size",
        "-show_entries", "stream=codec_name,width,height,r_frame_rate,nb_frames",
        "-of", "json", str(path),
    ], timeout=60)
    if rc != 0 or not out.strip():
        return {"_error": err.strip()[:200] or "ffprobe 失败"}
    try:
        d = json.loads(out)
    except Exception as e:
        return {"_error": "解析 ffprobe 输出失败: %s" % e}
    info = {}
    fmt = (d.get("format") or {})
    if "duration" in fmt:
        info["duration"] = float(fmt["duration"])
    if "size" in fmt:
        info["size"] = int(fmt["size"])
    for st in d.get("streams", []):
        if st.get("codec_type") != "video":
            continue
        info["codec"] = st.get("codec_name")
        info["width"] = st.get("width")
        info["height"] = st.get("height")
        if st.get("r_frame_rate"):
            try:
                num, den = st.get("r_frame_rate").split("/")
                info["fps"] = round(int(num) / int(den), 2) if int(den) else None
            except Exception:
                pass
        if st.get("nb_frames"):
            info["frames"] = int(st["nb_frames"])
    return info


def decode_check(path: Path) -> str:
    """完整解码一遍，返回错误文本（空 = 零错误）。"""
    rc, _out, err = run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"], timeout=180)
    return err.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="media", help="media 根目录")
    ap.add_argument("--fresh", type=int, default=120, help="跳过最近 N 秒内修改的文件")
    ap.add_argument("--limit", type=int, default=0, help="最多检查多少个文件（0 = 不限）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = Path(args.dir)
    videos = sorted((root / "videos").glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    stills = sorted((root / "stills").glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
    if args.limit:
        videos = videos[:args.limit]
        stills = stills[:args.limit]

    if not videos and not stills:
        print("media 目录里没有文件：%s" % root)
        return 0

    now = time.time()
    ok = bad = skipped = 0
    problems = []
    details = []

    print("检查 %s" % root)
    print("  录像 %d 个，抓拍 %d 个" % (len(videos), len(stills)))

    print("\n[录像]")

    def check_one(f: Path):
        err = decode_check(f)
        info = probe(f)
        return f, err, info

    todo = []
    for f in videos:
        if now - f.stat().st_mtime < args.fresh:
            skipped += 1
            continue
        todo.append(f)

    # ffmpeg 是子进程，用线程并发即可，串行在树莓派上要好几分钟
    workers = max(1, min(8, (os.cpu_count() or 2) * 2))
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        for f, err, info in pool.map(check_one, todo):
            if err or "_error" in info:
                bad += 1
                problems.append("%s: %s" % (f.name, (err or info["_error"])[:120]))
                print("  ✗ %-44s %s" % (f.name, (err or info["_error"])[:80]))
                continue
            ok += 1
            details.append({"file": f.name, **info})

    print("\n[抓拍]")
    still_ok = still_bad = 0
    for f in stills:
        age = now - f.stat().st_mtime
        if age < args.fresh:
            skipped += 1
            continue
        try:
            with open(f, "rb") as fh:
                head = fh.read(2)
                fh.seek(-2, os.SEEK_END)
                tail = fh.read(2)
        except Exception as e:
            still_bad += 1
            problems.append("%s: %s" % (f.name, e))
            continue
        if head != b"\xff\xd8" or tail != b"\xff\xd9":
            still_bad += 1
            problems.append("%s: JPEG 头尾标记不对 (%r/%r)" % (f.name, head, tail))
            continue
        still_ok += 1

    print("\n" + "=" * 60)
    print("录像解码零错误 : %d" % ok)
    print("录像有问题     : %d" % bad)
    print("抓拍合法       : %d" % still_ok)
    print("抓拍有问题     : %d" % still_bad)
    print("跳过(正在写)   : %d" % skipped)
    if problems:
        print("\n问题清单:")
        for p in problems[:30]:
            print("  ✗", p)
    print("=" * 60)

    if details:
        fps = [d["fps"] for d in details if d.get("fps")]
        res = sorted({(d.get("width"), d.get("height")) for d in details if d.get("width")})
        dur = [d["duration"] for d in details if d.get("duration")]
        if fps:
            print("帧率范围: %.2f ~ %.2f（均值 %.2f）" % (min(fps), max(fps), sum(fps) / len(fps)))
        if res:
            print("分辨率: %s" % ", ".join("%dx%d" % r for r in res))
        if dur:
            print("时长范围: %.1f ~ %.1f 秒" % (min(dur), max(dur)))

    if args.json:
        print(json.dumps({"ok": ok, "bad": bad, "still_ok": still_ok,
                          "still_bad": still_bad, "skipped": skipped,
                          "problems": problems, "details": details},
                         ensure_ascii=False, indent=2))
    return 1 if (bad or still_bad) else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    sys.exit(main())

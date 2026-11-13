"""事件录制：预录缓冲 + 边录边编码 + 缩略图 + 事件索引。

录制流程（对齐官方 PiKrellCam 的 pre/post capture 语义）：
  * 持续维护一个环形缓冲，保存最近 pre_seconds 秒的 JPEG 帧
  * 侦测到移动的瞬间触发事件，把缓冲里的预录帧 + 当前帧一起写入 ffmpeg
  * 移动结束后继续录制 post_seconds 秒
  * ffmpeg 以 image2pipe 方式边收帧边编码，不产生中间文件、不二次读盘
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

from .util import jpeg_crop, jpeg_thumbnail

try:
    from PIL import Image
    import io
except Exception:  # noqa: BLE001
    Image = None


def _mp4_has_moov(path: Path) -> bool:
    """检查 MP4 是否含**完整**的 moov atom（缺 moov 的文件无法播放）。

    不能只搜 b"moov" 字符串：被截断的 moov 头部也含这个关键字，但解析必然失败。
    这里按 ISO-BMFF 的 top-level atom 结构逐个走一遍：
      [4B size][4B type][payload]，size==1 表示后跟 8 字节 largesize，size==0 表示延伸到文件尾。
    只要找到一个声明长度完全落在文件内的 moov 就算有效。
    """
    try:
        size = path.stat().st_size
        if size <= 0:
            return False
        with open(path, "rb") as fh:
            offset = 0
            while offset + 8 <= size:
                fh.seek(offset)
                hdr = fh.read(16)
                if len(hdr) < 8:
                    break
                asize = int.from_bytes(hdr[0:4], "big")
                atype = hdr[4:8]
                header = 8
                if asize == 1:
                    if len(hdr) < 16:
                        break
                    asize = int.from_bytes(hdr[8:16], "big")
                    header = 16
                elif asize == 0:
                    asize = size - offset
                if asize < header:
                    break
                if atype == b"moov":
                    # moov 必须完整落在文件范围内，否则是半截的
                    return (offset + asize) <= size
                if (offset + asize) > size:
                    break           # 声明长度超出文件 → 已被截断
                offset += asize

            # 兜底：moov 在文件尾（未启用 faststart 的旧文件）
            tail_len = min(size, 1 << 20)
            fh.seek(size - tail_len)
            tail = fh.read(tail_len)
            idx = tail.rfind(b"moov")
            if idx >= 4:
                msize = int.from_bytes(tail[idx - 4:idx], "big")
                if msize >= 8 and (size - tail_len + idx - 4 + msize) <= size:
                    return True
            return False
    except Exception:
        # 检测不了就保守认为有效，避免误删正常录像
        return True


class Recorder:
    def __init__(self, config, state, on_event=None):
        self.config = config
        self.state = state
        self.on_event = on_event          # 回调 (name, payload)
        self._lock = threading.RLock()
        self._buffer: deque = deque()     # (ts, jpeg)
        self._proc: subprocess.Popen | None = None
        self._event_id: str | None = None
        self._event_start = 0.0
        self._event_frames = 0
        self._last_motion_at = 0.0
        self._in_event = False
        self._last_event_end = 0.0
        self._last_keyframe: bytes | None = None
        self._last_bbox = None
        self._event_algorithm: str | None = None
        self._event_region: str | None = None
        self._event_bbox = None
        self._encoder_stuck = False
        self._encoder_fail_at = 0.0
        self._ffmpeg_err_fh = None
        self._tmp = Path("/tmp/pikrellcam-lite")
        self._events: list[dict] = []
        # 事件索引固定放在内置存储：外部存储拔出/换盘时索引不会丢
        self._events_file = config.internal_media_dir() / "events.json"
        self._legacy_events_file = config.media_sub("events.json")
        self._load_events()
        # 事件总数要在启动时就同步到运行时状态，否则重启后顶栏的"事件"计数
        # 会一直显示 0，直到下一个事件结束才更新。
        self.state.set("events_total", len(self._events))
        self._sweep_broken_videos()

    # ------------------------------------------------------------------
    def _load_events(self):
        try:
            if self._events_file.exists():
                self._events = json.loads(self._events_file.read_text())
            elif self._legacy_events_file.exists():
                # 兼容旧版本：索引曾经跟着 media.dir 放在外部存储里
                self._events = json.loads(self._legacy_events_file.read_text())
            else:
                self._events = []
        except Exception:
            self._events = []

    def _save_events(self):
        try:
            self._events_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._events_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._events, indent=2, ensure_ascii=False))
            os.replace(tmp, self._events_file)
        except Exception:
            pass

    @property
    def events(self) -> list[dict]:
        with self._lock:
            return list(self._events)

    # ------------------------------------------------------------------
    def _sweep_broken_videos(self):
        """启动时清理上次异常退出留下的坏文件。

        服务被 SIGKILL / 断电时 ffmpeg 来不及写 moov，这些 mp4 播放器打不开，
        留着只会让录像列表里出现点不开的条目。启动时扫一遍直接清掉。
        """
        videos = self.config.media_sub("videos")
        if not videos.exists():
            return
        broken = []
        for f in videos.glob("*.mp4"):
            try:
                if not _mp4_has_moov(f):
                    broken.append(f)
            except Exception:
                continue
        if not broken:
            return
        with self._lock:
            names = {f.name for f in broken}
            before = len(self._events)
            self._events = [e for e in self._events if e.get("video") not in names]
            if len(self._events) != before:
                self._save_events()
        for f in broken:
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
        self.state.set("error", f"已清理 {len(broken)} 个未正常收尾的录像文件")

    # ------------------------------------------------------------------
    def _encoder_cmd(self, out_path: Path, force: str | None = None) -> tuple[list[str], str]:
        fps = max(1, int(self.config.get("camera", "fps", default=10)))
        quality = int(self.config.get("record", "quality", default=23))
        want = (force or self.config.get("record", "encoder", default="auto") or "auto").lower()

        base = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(fps), "-i", "-",
        ]
        tail = ["-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_path)]

        if want == "libx264":
            return base + ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(quality)] + tail, "libx264"
        if want == "h264_v4l2m2m":
            return base + ["-c:v", "h264_v4l2m2m", "-b:v", "4M"] + tail, "h264_v4l2m2m"
        # auto: Pi 4/5 有硬件 H.264 编码器，优先使用；失败自动回退
        if Path("/dev/video31").exists() or self._has_m2m_encoder():
            return base + ["-c:v", "h264_v4l2m2m", "-b:v", "4M"] + tail, "h264_v4l2m2m"
        return base + ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(quality)] + tail, "libx264"

    def _has_m2m_encoder(self) -> bool:
        try:
            out = subprocess.run(
                ["v4l2-ctl", "--list-devices"], capture_output=True, timeout=5
            ).stdout.decode("utf-8", "replace")
            return "bcm2835-codec" in out
        except Exception:
            return False

    # ------------------------------------------------------------------
    def on_frame(self, frame: bytes, now: float, motion: bool = False, bbox=None,
                 algorithm: str | None = None, region: str | None = None) -> None:
        """采集线程每帧调用。"""
        if self.config.get("record", "paused", default=False):
            # 暂停录像时，若还有没收尾的事件要先正常收尾：否则 ffmpeg 收不到
            # EOF 也不会退出，会一直挂着，白占着硬件编码器和管道。
            if self._in_event or self._proc is not None:
                with self._lock:
                    if self._in_event or self._proc is not None:
                        self._finish_event(now)
            return
        with self._lock:
            if not self._in_event:
                self._buffer.append((now, frame))
                pre = float(self.config.get("record", "pre_seconds", default=5))
                fps = max(1, int(self.config.get("camera", "fps", default=10)))
                maxlen = max(1, int(pre * fps))
                while len(self._buffer) > maxlen:
                    self._buffer.popleft()

            gap = float(self.config.get("record", "event_gap_seconds", default=0))
            can_start = (now - self._last_event_end) >= gap

            if not self._in_event:
                if motion and can_start:
                    self._start_event(frame, now, bbox, algorithm, region)
                return

            # 事件进行中
            if not self._write(frame):
                # 编码器已卡死/退出：结束本事件，服务继续正常工作
                self._finish_event(now)
                return
            self._last_keyframe = frame
            if bbox:
                self._last_bbox = bbox
            if motion:
                self._last_motion_at = now
            else:
                post = float(self.config.get("record", "post_seconds", default=8))
                if (now - self._last_motion_at) >= post:
                    self._finish_event(now)
                    return
            max_event = float(self.config.get("record", "max_event_seconds", default=120))
            if (now - self._event_start) >= max_event:
                self._finish_event(now)

    # ------------------------------------------------------------------
    def _spawn_encoder(self, cmd: list[str]):
        """启动 ffmpeg 编码进程。

        stderr 必须落文件而不是 PIPE：PIPE 没人读，一旦 ffmpeg 输出较多错误信息
        就会写满管道缓冲区进而卡死自己。
        """
        self._tmp.mkdir(parents=True, exist_ok=True)
        try:
            err_fh = open(self._tmp / "ffmpeg-err.log", "ab", buffering=0)
        except Exception:
            err_fh = subprocess.DEVNULL
        self._ffmpeg_err_fh = err_fh
        return subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err_fh,
        )

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    def _storage_ready(self) -> bool:
        """写媒体前的实时校验。

        外部存储最危险的失败模式是"U 盘拔出后路径依然存在"——它只是
        变成了 SD 卡上的一个空目录。这时若继续录像，文件会悄悄写回
        SD 卡，把根分区撑爆，树莓派直接变砖。

        所以每次开新事件前都确认一次：目标必须此刻仍是挂载点。
        """
        try:
            ok, reason, _ = self.config.media_write_target()
        except Exception:
            return True
        if not ok:
            self.state.set("error", f"存储不可用，已暂停录像：{reason}")
            return False
        return True

    def _start_event(self, frame: bytes, now: float, bbox=None,
                      algorithm: str | None = None, region: str | None = None):
        # 存储不可用时直接放弃本次事件（不启动 ffmpeg）
        if not self._storage_ready():
            return
        self._event_id = time.strftime("%Y%m%d_%H%M%S")
        self._event_start = now
        self._event_frames = 0
        self._last_motion_at = now
        self._in_event = True
        self._event_algorithm = algorithm
        self._event_region = region
        self._event_bbox = bbox
        self._tmp.mkdir(parents=True, exist_ok=True)

        # 编码器刚刚卡死过：进入冷却期，不再反复尝试。否则每个运动事件都会
        # 白等一次写超时，采集线程会明显变慢。
        cool = float(self.config.get("record", "encoder_cooldown", default=60) or 60)
        if self._encoder_stuck and (time.time() - self._encoder_fail_at) < cool:
            self._in_event = False
            self._event_id = None
            return
        self._encoder_stuck = False

        out = self.config.media_sub("videos") / f"{self._event_id}.mp4"
        cmd, enc = self._encoder_cmd(out)
        self._encoder_name = enc
        try:
            self._proc = self._spawn_encoder(cmd)
        except Exception as exc:  # noqa: BLE001
            self.state.set("error", f"ffmpeg 启动失败: {exc}")
            self._proc = None
            self._in_event = False
            return
        # 预录帧
        ok = True
        for _, buf in list(self._buffer):
            ok = self._write(buf) and ok
        ok = self._write(frame) and ok

        # 硬件编码器是在写第一帧时才真正初始化的，若此时失败（例如设备被占用），
        # 录像会留下 0 字节文件。这里回退到软件编码器重试一次。
        want = (self.config.get("record", "encoder", default="auto") or "auto").lower()
        if not ok and want == "auto" and enc != "libx264":
            try:
                self._proc.kill()
            except Exception:
                pass
            cmd2, enc2 = self._encoder_cmd(out, force="libx264")
            self._encoder_name = enc2
            try:
                self._proc = self._spawn_encoder(cmd2)
            except Exception as exc:  # noqa: BLE001
                self.state.set("error", f"ffmpeg 启动失败: {exc}")
                self._proc = None
                self._in_event = False
                return
            ok = True
            for _, buf in list(self._buffer):
                ok = self._write(buf) and ok
            ok = self._write(frame) and ok
            self.state.set("error", "硬件编码器不可用，已回退到软件编码器")

        self._buffer.clear()
        self.state.update(recording=True)
        if self.on_event:
            try:
                self.on_event("on_motion_begin", {"id": self._event_id})
            except Exception:
                pass

    def _write(self, frame: bytes) -> bool:
        """把一帧写进 ffmpeg 的 stdin。

        ffmpeg 启动失败或卡住（比如硬件编码器被占用）时它不再消费管道，
        这里写帧就会一直阻塞，而调用方是**采集线程**——阻塞会把整个服务卡死
        （表现为画面停住、接口无响应，且录像文件留下 0 字节）。

        所以写入放到独立线程里并限时等待：超时就判定编码器卡死，放弃本事件，
        服务继续正常运行。返回 False 表示本次写入失败/卡死。
        """
        proc = self._proc
        if not proc or not proc.stdin:
            return False
        err: list[BaseException] = []

        def _do():
            try:
                proc.stdin.write(frame)
            except BaseException as exc:  # noqa: BLE001
                err.append(exc)

        timeout = float(self.config.get("record", "frame_write_timeout", default=8) or 8)
        t = threading.Thread(target=_do, daemon=True)
        t.start()
        t.join(timeout=timeout)
        if t.is_alive():
            # 管道写不动了：ffmpeg 不再消费，判定编码器卡死
            self._proc = None
            self._encoder_stuck = True
            self._encoder_fail_at = time.time()
            try:
                proc.kill()
            except Exception:
                pass
            return False
        if err:
            self._proc = None
            self._encoder_stuck = True
            self._encoder_fail_at = time.time()
            return False
        self._event_frames += 1
        return True

    def _close_encoder(self, proc: subprocess.Popen) -> bool:
        """让 ffmpeg 正常收尾。

        ffmpeg 以 image2pipe 读 stdin 收帧，**阻塞在读 stdin 时任何信号都不会让它写出
        moov atom**（SIGTERM/SIGINT 均会挂起直到被 SIGKILL），只有 stdin 收到 EOF
        才会走正常的 trailer 写出流程。所以收尾的唯一可靠方式就是关掉 stdin 再等它退出。

        返回 True 表示 moov 已正常写出（文件可播放）。
        """
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
        except Exception:
            pass
        fh = getattr(self, "_ffmpeg_err_fh", None)
        if fh is not None and fh is not subprocess.DEVNULL:
            try:
                fh.close()
            except Exception:
                pass
            self._ffmpeg_err_fh = None
        timeout = float(self.config.get("record", "encoder_close_timeout", default=15) or 15)
        try:
            proc.wait(timeout=timeout)
            return True
        except Exception:
            # ffmpeg 异常卡死：先礼后兵，但强杀会导致 moov 缺失，文件不可播放
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=3)
                return True
            except Exception:
                pass
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.wait(timeout=3)
            except Exception:
                pass
            return False

    def _finish_event(self, now: float):
        proc = self._proc
        self._proc = None
        closed_ok = True
        if proc:
            closed_ok = self._close_encoder(proc)

        self._in_event = False
        self._last_event_end = now
        self.state.update(recording=False)

        eid = self._event_id
        self._event_id = None
        if not eid:
            return

        video = self.config.media_sub("videos") / f"{eid}.mp4"
        if not video.exists() or video.stat().st_size == 0:
            # 空文件没有任何价值，直接清掉，别让录像列表里出现打不开的条目
            video.unlink(missing_ok=True)
            if self.on_event:
                try:
                    self.on_event("on_motion_end", {"id": eid, "ok": False})
                except Exception:
                    pass
            return

        # moov 完整性校验：ffmpeg 被强杀时写不出 moov，这类文件播放器打不开，
        # 留在目录里只会让用户以为录上了却点不开。直接剔除并清理。
        if not closed_ok or not _mp4_has_moov(video):
            try:
                self.state.set("error", f"录像 {eid}.mp4 未正常收尾，已清理")
            except Exception:
                pass
            video.unlink(missing_ok=True)
            if self.on_event:
                try:
                    self.on_event("on_motion_end", {"id": eid, "ok": False})
                except Exception:
                    pass
            return

        # 缩略图：整帧 + 运动目标裁剪
        stills = self.config.media_sub("stills")
        stills.mkdir(parents=True, exist_ok=True)
        thumb_name = f"{eid}.jpg"
        obj_name = f"{eid}_obj.jpg"
        src = self._last_keyframe
        if src:
            full = jpeg_thumbnail(src, (320, 180))
            if full:
                (stills / thumb_name).write_bytes(full)
            box = self._last_bbox
            if box:
                crop = self._crop_box(src, box)
                if crop:
                    (stills / obj_name).write_bytes(crop)

        fps = max(1, int(self.config.get("camera", "fps", default=10)))
        entry = {
            "id": eid,
            "video": video.name,
            "thumb": thumb_name,
            "thumb_object": obj_name,
            "start": self._event_start,
            "end": now,
            "duration": round(self._event_frames / fps, 1),
            "frames": self._event_frames,
            "size": video.stat().st_size,
            "encoder": getattr(self, "_encoder_name", ""),
            "algorithm": getattr(self, "_event_algorithm", None),
            "region": getattr(self, "_event_region", None),
        }
        with self._lock:
            self._events.insert(0, entry)
            self._save_events()
        self.state.set("events_total", len(self._events))
        self._purge_if_needed()
        if self.on_event:
            try:
                self.on_event("on_motion_end", {**entry, "ok": True})
            except Exception:
                pass

    def _crop_box(self, src: bytes, box) -> bytes | None:
        """把检测分辨率下的包围盒换算到原始帧坐标并裁剪。"""
        try:
            import io as _io
            with Image.open(_io.BytesIO(src)) as im:
                fw, fh = im.size
        except Exception:
            return None
        dw, dh = self.config.get("camera", "detect_resolution", default=[320, 180])
        sx = fw / max(1, dw)
        sy = fh / max(1, dh)
        x0, y0, x1, y1 = [int(v) for v in box]
        full = (x0 * sx, y0 * sy, x1 * sx, y1 * sy)
        return jpeg_crop(src, full, (240, 240))

    # ------------------------------------------------------------------
    def _purge_if_needed(self):
        limit_gb = float(self.config.get("record", "max_disk_gb", default=8) or 0)
        if limit_gb <= 0:
            return
        videos = self.config.media_sub("videos")
        stills = self.config.media_sub("stills")
        limit = limit_gb * 1024 ** 3
        files = sorted(videos.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
        total = sum(f.stat().st_size for f in files)
        idx = 0
        while total > limit and idx < len(files):
            f = files[idx]
            total -= f.stat().st_size
            with self._lock:
                self._events = [e for e in self._events if e.get("video") != f.name]
                self._save_events()
            f.unlink(missing_ok=True)
            (stills / f"{f.stem}.jpg").unlink(missing_ok=True)
            (stills / f"{f.stem}_obj.jpg").unlink(missing_ok=True)
            idx += 1

    # ------------------------------------------------------------------
    def delete_event(self, eid: str) -> bool:
        with self._lock:
            before = len(self._events)
            self._events = [e for e in self._events if e.get("id") != eid]
            if len(self._events) == before:
                return False
            self._save_events()
        videos = self.config.media_sub("videos")
        stills = self.config.media_sub("stills")
        (videos / f"{eid}.mp4").unlink(missing_ok=True)
        (stills / f"{eid}.jpg").unlink(missing_ok=True)
        (stills / f"{eid}_obj.jpg").unlink(missing_ok=True)
        self.state.set("events_total", len(self._events))
        return True

    def purge(self, what: str = "all") -> int:
        videos = self.config.media_sub("videos")
        stills = self.config.media_sub("stills")
        n = 0
        if what in ("all", "videos"):
            for f in videos.glob("*"):
                f.unlink(missing_ok=True); n += 1
        if what in ("all", "stills"):
            for f in stills.glob("*"):
                f.unlink(missing_ok=True); n += 1
        with self._lock:
            if what in ("all", "videos"):
                self._events = []
                self._save_events()
        self.state.set("events_total", len(self._events))
        return n

    def stop(self):
        with self._lock:
            if self._in_event or self._proc is not None:
                self._finish_event(time.time())

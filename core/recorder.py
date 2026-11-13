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

from .util import dir_size, jpeg_crop, jpeg_thumbnail

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
    def __init__(self, config, state, on_event=None, log=None):
        self.config = config
        self.state = state
        self.on_event = on_event          # 回调 (name, payload)
        self.log = log                    # 日志回调 (msg)
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
        # --- 循环录像（loop） ---
        # 与事件录像**互斥**：硬件编码器同一时刻只能有一个 ffmpeg 实例，
        # 所以 loop 段与事件不能并行写。检测到移动时 loop 让位，事件结束后恢复。
        self._loop_enabled = False
        self._loop_active = False
        self._loop_proc: subprocess.Popen | None = None
        self._loop_id: str | None = None
        self._loop_start = 0.0
        self._loop_frames = 0
        self._loop_index = 0
        self._loop_stuck = False
        self._loop_fail_at = 0.0
        self._loop_yielded = False
        self._loop_closed = 0
        self._loop_bytes = 0
        self._loop_scan_at = 0.0
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
    def _encoder_cmd(self, out_path: Path, force: str | None = None,
                     quality: int | None = None) -> tuple[list[str], str]:
        fps = max(1, int(self.config.get("camera", "fps", default=10)))
        if quality is None:
            quality = int(self.config.get("record", "quality", default=23))
        else:
            quality = int(quality)
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
            # 循环录像段同样要收尾，不然会留下一个缺 moov 的坏文件
            if self._loop_active or self._loop_proc is not None:
                with self._lock:
                    if self._loop_active or self._loop_proc is not None:
                        self._finish_loop_segment(now)
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
                    # 事件优先：循环录像让位，把硬件编码器交给事件录像。
                    if self._loop_active:
                        self._finish_loop_segment(now)
                    self._start_event(frame, now, bbox, algorithm, region)
                    return
                # 没有事件（或事件间隔未到）：循环录像继续写。
                self._loop_tick(frame, now)
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
        同时看一眼目标文件系统的剩余空间——写满了照样会把盘撑爆。
        """
        try:
            ok, reason, _ = self.config.media_write_target()
        except Exception:
            ok, reason = True, ""
        if not ok:
            self.state.set("error", f"存储不可用，已暂停录像：{reason}")
            return False
        try:
            _, free = self._disk_space()
            min_free = self._min_free_bytes()
            if min_free > 0 and free < min_free:
                # 不写 state.error：那是"最近一次错误"且永不清空，
                # 磁盘空间是可恢复的，挂在红字里反而误导。
                self.state.update(disk_low=True,
                                  disk_reason=(f"磁盘剩余空间不足"
                                               f"（剩 {free // (1024 ** 2)} MB）"))
                return False
        except Exception:
            pass
        return True

    def _start_event(self, frame: bytes, now: float, bbox=None,
                      algorithm: str | None = None, region: str | None = None):
        # 存储不可用时直接放弃本次事件（不启动 ffmpeg）
        if not self._storage_ready():
            return
        # 循环录像让位：事件期间 loop 处于暂停状态
        self._loop_yielded = bool(self.config.get("loop", "enabled", default=False))
        self.state.update(loop_yielded=self._loop_yielded)
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
        # 事件结束 → 循环录像可以恢复（下一帧就会开新段）
        self._loop_yielded = False
        self.state.update(loop_yielded=False)
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
        self.check_disk()
        if self.on_event:
            try:
                self.on_event("on_motion_end", {**entry, "ok": True})
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 循环录像（loop）
    #
    # 与上游一致的语义：持续录像、按固定时长切段、超出配额就删最旧的段。
    # 与上游不同的是**互斥**这一条必须做对：
    #
    #   树莓派的 H.264 硬件编码器走 /dev/video31，同一时刻只能有一个
    #   ffmpeg 实例在用。lite 的采集线程是单线程喂帧的，所以 loop 段和
    #   事件录像**不可能并行**。真要并行，第二路要么退化成软件编码
    #   （CPU 扛不住），要么直接把硬件编码器抢走导致另一个卡死。
    #
    #   所以这里走状态互斥：检测到移动 → loop 收尾让位 → 事件录像 →
    #   事件结束 → loop 自动恢复（下一帧重新开一段）。
    # ------------------------------------------------------------------
    def _loop_tick(self, frame: bytes, now: float) -> None:
        """循环录像的逐帧处理。调用方已持有 self._lock。"""
        if not self.config.get("loop", "enabled", default=False):
            if self._loop_active or self._loop_proc is not None:
                self._finish_loop_segment(now)
            return

        if self._loop_active:
            seg = self._loop_segment_seconds()
            if (now - self._loop_start) >= seg:
                # 段用满了：收尾并开新段（用当前帧当新段的第 1 帧）
                self._finish_loop_segment(now)
                self._start_loop_segment(frame, now)
                return
            if not self._write_loop(frame):
                # 编码器卡死：收掉这一段，下一帧重新开始
                self._finish_loop_segment(now)
            return

        self._start_loop_segment(frame, now)

    def _loop_segment_seconds(self) -> float:
        try:
            seg = float(self.config.get("loop", "segment_seconds", default=60) or 60)
        except (TypeError, ValueError):
            seg = 60.0
        return max(5.0, min(3600.0, seg))

    def _start_loop_segment(self, frame: bytes, now: float) -> None:
        """开一个新的循环录像段。调用方已持有 self._lock。"""
        if not self._storage_ready():
            return
        cool = float(self.config.get("record", "encoder_cooldown", default=60) or 60)
        if self._loop_stuck and (time.time() - self._loop_fail_at) < cool:
            # 编码器刚刚卡死过，冷却期内不再反复尝试
            return
        self._loop_stuck = False

        d = self.config.loop_dir()
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001
            self.state.set("error", f"循环录像目录不可用: {exc}")
            return

        self._loop_index += 1
        name = "loop_%s_%04d.mp4" % (time.strftime("%Y%m%d_%H%M%S"), self._loop_index)
        out = d / name
        try:
            quality = int(self.config.get("loop", "quality", default=26) or 26)
        except (TypeError, ValueError):
            quality = 26
        cmd, enc = self._encoder_cmd(out, quality=quality)
        self._encoder_name = enc
        try:
            self._loop_proc = self._spawn_encoder(cmd)
        except Exception as exc:  # noqa: BLE001
            self.state.set("error", f"循环录像启动失败: {exc}")
            self._loop_proc = None
            return

        self._loop_active = True
        self._loop_id = name
        self._loop_start = now
        self._loop_frames = 0
        self._write_loop(frame)
        self.state.update(loop_recording=True)

    def _write_loop(self, frame: bytes) -> bool:
        """把一帧写进循环录像的 ffmpeg。

        与事件录像的 _write 分开：循环录像卡死时不能把事件录像也一起
        拖下水（事件的冷却期会让移动录像整整一分钟录不上）。
        """
        proc = self._loop_proc
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
        if t.is_alive() or err:
            self._loop_proc = None
            self._loop_stuck = True
            self._loop_fail_at = time.time()
            try:
                proc.kill()
            except Exception:
                pass
            return False
        self._loop_frames += 1
        return True

    def _finish_loop_segment(self, now: float) -> None:
        """收尾当前循环录像段。调用方已持有 self._lock。"""
        proc = self._loop_proc
        self._loop_proc = None
        was_active = self._loop_active
        self._loop_active = False
        self.state.update(loop_recording=False)
        if not was_active and proc is None:
            self._loop_id = None
            return

        closed_ok = True
        if proc:
            closed_ok = self._close_encoder(proc)

        name = self._loop_id
        self._loop_id = None
        self._loop_frames = 0
        if not name:
            return
        path = self.config.loop_dir() / name
        try:
            if not path.exists() or path.stat().st_size == 0:
                path.unlink(missing_ok=True)
                return
            if not closed_ok or not _mp4_has_moov(path):
                # 没收尾的文件播放器打不开，留着只会让列表里出现坏条目
                path.unlink(missing_ok=True)
                self._log(f"loop 段 {name} 未正常收尾，已清理")
                return
        except OSError:
            return
        self._loop_closed += 1
        try:
            self._loop_bytes += path.stat().st_size
        except OSError:
            pass
        self._loop_check_disk()

    def _oldest_loop_files(self) -> list[Path]:
        """循环录像目录下的段文件，按修改时间从旧到新排好。"""
        d = self.config.loop_dir()
        out: list[tuple[float, Path]] = []
        try:
            for p in d.iterdir():
                try:
                    if p.is_file() and p.suffix.lower() == ".mp4":
                        out.append((p.stat().st_mtime, p))
                except OSError:
                    continue
        except OSError:
            return []
        out.sort(key=lambda x: x[0])
        return [p for _, p in out]

    def _drop_loop(self, path: Path) -> int:
        """删掉一个循环录像段，返回释放的字节数。"""
        freed = 0
        try:
            freed = path.stat().st_size
        except OSError:
            pass
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return freed

    def _loop_check_disk(self) -> int:
        """按**文件系统总容量的百分比**控制循环录像占用。

        与上游的 loop_diskusage_percent 口径一致：算的是"占整块盘多少"，
        而不是"占媒体目录多少"。这样换存储目标时百分比依然有意义。

        超限时删最旧的段——循环录像本来就是覆盖式录像，旧的让位给新的
        是它本来的语义，事件录像不受影响。
        """
        try:
            pct = float(self.config.get("loop", "max_disk_percent", default=30) or 0)
        except (TypeError, ValueError):
            pct = 0.0
        if pct <= 0:
            return 0
        total, _free = self._disk_space()
        if total <= 0:
            return 0
        limit = int(total * pct / 100.0)
        d = self.config.loop_dir()
        used = dir_size(d)
        removed = 0
        if used > limit:
            for path in self._oldest_loop_files():
                if used <= limit:
                    break
                used -= self._drop_loop(path)
                removed += 1
        if removed:
            self._log("loop guard: removed %d old loop segment(s); "
                      "loop usage %.1f MB / limit %.1f MB (%.0f%% of disk)"
                      % (removed, used / 1024 ** 2, limit / 1024 ** 2, pct))
        return removed

    def set_loop_enabled(self, enabled: bool) -> dict:
        """开关循环录像。"""
        enabled = bool(enabled)
        self.config.set({"loop": {"enabled": enabled}})
        with self._lock:
            self._loop_enabled = enabled
            if not enabled and (self._loop_active or self._loop_proc is not None):
                self._finish_loop_segment(time.time())
        return self.loop_stats()

    def loop_stats(self) -> dict:
        """循环录像的运行时状态。"""
        now = time.time()
        with self._lock:
            # 目录扫描有点贵（段多了就是几百个文件），限频 5 秒一次
            if now - self._loop_scan_at > 5.0:
                self._loop_scan_at = now
                files = self._oldest_loop_files()
                # 正在录的那一段可能已经在目录里了（ffmpeg 一开始就建文件），
                # 但它还没收尾，所以要从"已收尾段数"里扣掉。
                active_on_disk = 0
                if self._loop_active and self._loop_id:
                    try:
                        if (self.config.loop_dir() / self._loop_id).exists():
                            active_on_disk = 1
                    except OSError:
                        pass
                self._loop_closed = max(0, len(files) - active_on_disk)
                total = 0
                for f in files:
                    try:
                        total += f.stat().st_size
                    except OSError:
                        continue
                self._loop_bytes = total
            closed = self._loop_closed
            used = self._loop_bytes
            active = self._loop_active
            current = self._loop_id
            yielded = self._loop_yielded

        try:
            total_bytes, free_bytes = self._disk_space()
        except Exception:
            total_bytes, free_bytes = 0, 0
        try:
            pct = float(self.config.get("loop", "max_disk_percent", default=30) or 0)
        except (TypeError, ValueError):
            pct = 0.0
        limit = int(total_bytes * pct / 100.0) if pct > 0 else 0
        seg_count = int(closed) + (1 if active else 0)
        try:
            self.state.update(loop_segments=seg_count, loop_bytes=int(used))
        except Exception:
            pass
        return {
            "enabled": bool(self.config.get("loop", "enabled", default=False)),
            "recording": bool(active),
            "yielded": bool(yielded),
            # 段数 = 已收尾的段 + 正在录的这一段
            "segments": seg_count,
            "bytes": int(used),
            "current": current or "",
            "dir": str(self.config.loop_dir()),
            "segment_seconds": self._loop_segment_seconds(),
            "max_disk_percent": pct,
            "quality": int(self.config.get("loop", "quality", default=26) or 26),
            "limit_bytes": limit,
            "disk_total_bytes": int(total_bytes),
            "disk_free_bytes": int(free_bytes),
        }

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
    # 磁盘监测
    #
    # 两道护栏，缺一不可：
    #
    #   A. 媒体配额  record.max_disk_gb
    #      媒体目录（录像 + 抓拍 + 延时）的总占用超过配额时，删掉最旧的录像。
    #
    #   B. 剩余空间  record.min_free_gb
    #      目标文件系统的**可用空间**低于下限时，继续删旧媒体腾地方。
    #
    # B 是 A 的补充，不是重复：配额可以调得比整块盘还大（128 GB 的配额
    # 配一块 28.7 GB 的 SD 卡完全合法），此时配额永远触发不了，真正兜底
    # 的就是"文件系统还剩多少"。只看配额的话，录像会一路写到文件系统
    # 100% 满——ext4 根分区写满之后日志写不进去、配置存不下、连系统都
    # 可能起不来。
    #
    # 护栏 B 必须在**切换存储目标后立刻重算**：换到 U 盘之后，剩余空间
    # 跟 SD 卡完全是两回事，沿用旧值会做出错误判断。
    # ------------------------------------------------------------------
    def _disk_space(self) -> tuple[int, int]:
        """目标文件系统的 (总字节, 可用字节)。"""
        from . import storage as _storage
        try:
            return _storage.disk_usage(self.config.media_dir())
        except Exception:
            return (0, 0)

    def _oldest_files(self, sub: str) -> list[Path]:
        """某个媒体子目录下的文件，按修改时间从旧到新排好。"""
        d = self.config.media_sub(sub)
        out: list[tuple[float, Path]] = []
        if not d.exists():
            return []
        try:
            for p in d.iterdir():
                try:
                    if p.is_file():
                        out.append((p.stat().st_mtime, p))
                except OSError:
                    continue
        except OSError:
            return []
        out.sort(key=lambda x: x[0])
        return [p for _, p in out]

    def _drop_video(self, vpath: Path) -> int:
        """删掉一个录像及其附属抓拍，同时清掉事件索引。返回释放字节数。"""
        freed = 0
        stills = self.config.media_sub("stills")
        try:
            freed += vpath.stat().st_size
        except OSError:
            pass
        stem = vpath.stem
        for name in (f"{stem}.jpg", f"{stem}_obj.jpg"):
            sp = stills / name
            try:
                freed += sp.stat().st_size
            except OSError:
                pass
            try:
                sp.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            vpath.unlink(missing_ok=True)
        except OSError:
            pass
        with self._lock:
            self._events = [e for e in self._events if e.get("video") != vpath.name]
            self._save_events()
        return freed

    def _log(self, msg: str) -> None:
        if self.log:
            try:
                self.log(msg)
            except Exception:
                pass

    def _min_free_bytes(self) -> int:
        """剩余空间护栏的下限（字节）。0 = 关闭该护栏。"""
        try:
            gb = float(self.config.get("record", "min_free_gb", default=1) or 0)
        except (TypeError, ValueError):
            gb = 0
        return int(gb * 1024 ** 3)

    def refresh_disk_state(self) -> dict:
        """轻量刷新：只看目标文件系统的剩余空间，不遍历媒体目录。

        后台每 3 秒跑一次，不能干重活（遍历媒体目录在文件多时很贵）。
        """
        total, free = self._disk_space()
        min_free = self._min_free_bytes()
        low = min_free > 0 and free < min_free
        reason = ""
        if low:
            reason = (f"磁盘剩余空间不足（剩 {free // (1024 ** 2)} MB，"
                      f"低于下限 {min_free // (1024 ** 3)} GB）")
        try:
            self.state.update(
                disk_total_bytes=int(total),
                disk_free_bytes=int(free),
                disk_low=bool(low),
                disk_reason=reason,
            )
        except Exception:
            pass
        return {"total": total, "free": free, "low": low, "reason": reason}

    def check_disk(self) -> dict:
        """检查磁盘、按需清理，并返回本次检测结果。

        每个事件结束时调用；**切换存储目标后必须调用一次**——
        新目标的剩余空间和旧目标毫无关系。
        """
        quota = int(float(self.config.get("record", "max_disk_gb", default=8) or 0) * 1024 ** 3)
        min_free = self._min_free_bytes()

        media_dir = self.config.media_dir()
        used = dir_size(media_dir)
        total, free = self._disk_space()
        removed = 0

        # -- 护栏 A：媒体配额 -------------------------------------------
        if quota > 0 and used > quota:
            # 回收顺序：循环录像段 → 事件录像 → 延时摄影。
            # 循环录像本来就是覆盖式录像，旧的让位给新的正是它的语义；
            # 事件录像有明确的事件上下文，优先级高于循环录像段。
            for lpath in self._oldest_loop_files():
                if used <= quota:
                    break
                used -= self._drop_loop(lpath)
                removed += 1
            for vpath in self._oldest_files("videos"):
                if used <= quota:
                    break
                used -= self._drop_video(vpath)
                removed += 1
            total, free = self._disk_space()

        # -- 护栏 B：文件系统剩余空间 -----------------------------------
        if min_free > 0 and free < min_free:
            # 即便把全部媒体删光也补不上这个缺口 → 磁盘是被**别的东西**
            # 占满的（系统日志、别的应用、其它分区）。这时候删录像毫无
            # 意义，只会白白毁掉用户的录像历史。直接暂停录像并告警。
            media_total = dir_size(media_dir)
            if free + media_total >= min_free:
                # 先删循环录像段
                for lpath in self._oldest_loop_files():
                    if free >= min_free:
                        break
                    before = free
                    self._drop_loop(lpath)
                    removed += 1
                    _, free = self._disk_space()
                    if free <= before:
                        break
                # 再删最旧的录像（连带其抓拍）
                for vpath in self._oldest_files("videos"):
                    if free >= min_free:
                        break
                    before = free
                    self._drop_video(vpath)
                    removed += 1
                    _, free = self._disk_space()
                    if free <= before:
                        # 删了文件但空间没释放 → 空间被别的东西占着，
                        # 再删也没有意义，停下来保住剩下的历史。
                        break
                # 还不够就删延时文件：可再生，优先级低于事件录像
                if free < min_free:
                    for tpath in self._oldest_files("timelapse"):
                        if free >= min_free:
                            break
                        before = free
                        try:
                            tpath.unlink(missing_ok=True)
                            removed += 1
                        except OSError:
                            continue
                        _, free = self._disk_space()
                        if free <= before:
                            break
                used = dir_size(media_dir)

        st = self.refresh_disk_state()
        st["used"] = used
        st["removed"] = removed
        try:
            self.state.update(disk_used_bytes=int(used))
        except Exception:
            pass
        if removed:
            # 自动删了用户的录像，必须留痕——不然用户回头发现录像没了都不知道怎么回事
            self._log("disk guard: removed %d old media file(s); "
                      "free %.1f GB / %.1f GB, quota %s GB"
                      % (removed, free / 1024 ** 3, total / 1024 ** 3,
                         self.config.get("record", "max_disk_gb", default=8)))
        return st

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
        if what in ("all", "loop"):
            for f in self.config.loop_dir().glob("*"):
                f.unlink(missing_ok=True); n += 1
            with self._lock:
                self._loop_closed = 0
                self._loop_bytes = 0
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
            if self._loop_active or self._loop_proc is not None:
                self._finish_loop_segment(time.time())

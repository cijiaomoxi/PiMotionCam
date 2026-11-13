"""存储位置枚举与校验（支持 USB / SD 卡等外部存储）。

为什么需要这一层
----------------
`media.dir` 指向外部存储时，最危险的失败模式不是"写不进去"，
而是 **U 盘被拔出后路径依然存在**（它只是变成了 SD 卡上的一个空目录），
录像会继续往那里写，最终把根分区撑爆，树莓派直接变砖。

所以外部存储必须满足三个条件才允许写入：

1. 当前确实是**挂载点**（在 /proc/mounts 里能找到）
2. 挂载的是**可移动设备**或至少不是根文件系统
3. 实际可写（真实建一个临时文件试试，而不是只看权限位）

拔盘之后这些条件不再成立，服务会暂停录像并在界面上给出明确告警，
而不是把录像悄悄写回 SD 卡。

对外接口
--------
* :func:`enumerate_devices` —— 列出候选存储设备，供网页界面选择
* :func:`probe` —— 采集单个路径的存储状态
* :func:`check_target` —— 校验某个路径能否作为录像存储目标
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

# 候选挂载根目录：U 盘/移动硬盘在 Linux 上通常挂在这几个地方
_SCAN_ROOTS = ("/media", "/run/media", "/mnt", "/Volumes")

# 常见的一次性挂载点（U 盘直插 /media/usb 之类）
_SCAN_SINGLE = ("/media/usb", "/mnt/usb", "/media/usb0", "/media/usb1")

# 内部存储根分区的挂载点，视为"非外部存储"
_ROOT_FS = "/"


# ----------------------------------------------------------------------
# 基础工具
# ----------------------------------------------------------------------
def _read_mounts() -> dict[str, tuple[str, str]]:
    """返回 {挂载点: (设备, 文件系统类型)}。"""
    out: dict[str, tuple[str, str]] = {}
    try:
        with open("/proc/mounts", "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) < 3:
                    continue
                device, mount, fstype = parts[0], parts[1], parts[2]
                # 挂载点里的转义字符（\040 表示空格）
                mount = mount.replace("\\040", " ").replace("\\011", "\t")
                out[mount] = (device, fstype)
    except OSError:
        return {}
    return out


# 整盘设备名（本身不带分区号）。分区设备名在这些名字后面再加数字，
# 例如 sda1 是 sda 的分区，而 sda 本身就是整盘。
_WHOLE_DISK_RE = re.compile(
    r"^(?:loop|mmcblk|md|sr|fd|nbd|zram|ram)\d+$"
    r"|^(?:sd|hd|vd|xvd)[a-z]$"
    r"|^nvme\d+n\d+$"
    r"|^dm-\d+$"
)


def _sysfs_parent(name: str) -> str:
    """通过 sysfs 查分区设备所属的整盘设备名（查不到返回空串）。

    /sys/class/block/<分区>/.. 指向的正是整盘设备，这是最准的判断方式。
    """
    try:
        base = os.path.basename(os.path.realpath(f"/sys/class/block/{name}/.."))
    except OSError:
        return ""
    if not base or base == name:
        return ""
    # 整盘设备在 /sys/block/ 下有自己的目录
    if os.path.isdir(f"/sys/block/{base}"):
        return base
    return ""


def _parent_block_device(device: str) -> str:
    """把 /dev/sda1 这类分区设备还原成 /dev/sda 这样的整盘设备名。"""
    if not device.startswith("/dev/"):
        return ""
    name = device[len("/dev/"):]

    # 1) sysfs 最准：分区设备的上一级就是整盘
    parent = _sysfs_parent(name)
    if parent:
        return "/dev/" + parent

    # 2) sysfs 不可用时按命名规则解析
    #    mmcblk0p1 -> mmcblk0；nvme0n1p1 -> nvme0n1
    m = re.match(r"^(.*?)p(\d+)$", name)
    if m and m.group(1) and m.group(1)[-1].isdigit():
        return "/dev/" + m.group(1)
    #    sda1 -> sda；sdb12 -> sdb
    #    注意末尾数字段要整段取，不能去找字符 "0"——分区号是 1/2/3 时会找不到。
    if not _WHOLE_DISK_RE.match(name):
        m2 = re.match(r"^(.*?)(\d+)$", name)
        if m2 and m2.group(1):
            return "/dev/" + m2.group(1)
    return device


def _is_removable(device: str) -> bool:
    """通过 /sys 判断设备是否可移动（U 盘 / SD 卡）。"""
    if not device:
        return False
    block = _parent_block_device(device)
    name = block[len("/dev/"):] if block.startswith("/dev/") else ""
    if not name:
        return False
    for path in (f"/sys/block/{name}/removable",):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read().strip() == "1"
        except OSError:
            continue
    return False


def _fs_type(mount: str, mounts: dict[str, tuple[str, str]]) -> str:
    return mounts.get(mount, ("", ""))[1]


def _space(path: Path) -> tuple[int, int]:
    """返回 (总字节, 可用字节)。拿不到就返回 (0, 0)。"""
    try:
        st = os.statvfs(str(path))
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        return total, free
    except OSError:
        return 0, 0


def _really_writable(path: Path) -> bool:
    """真正建一个临时文件来验证可写性——权限位会骗人。"""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    try:
        fd, tmp = tempfile.mkstemp(prefix=".pkc-write-", dir=str(path))
        os.close(fd)
        os.unlink(tmp)
        return True
    except OSError:
        return False


def _human(n: int) -> str:
    if n <= 0:
        return "-"
    units = ("B", "KB", "MB", "GB", "TB")
    v = float(n)
    for u in units:
        if v < 1024 or u == units[-1]:
            return f"{v:.0f} {u}" if u == "B" else f"{v:.1f} {u}"
        v /= 1024
    return f"{v:.1f} TB"


# ----------------------------------------------------------------------
# 数据结构
# ----------------------------------------------------------------------
@dataclass
class StorageInfo:
    """一个候选存储位置的状态。"""

    path: str
    label: str = ""
    kind: str = "unknown"          # internal / usb / sdcard / external / unknown
    mounted: bool = False
    writable: bool = False
    removable: bool = False
    fs_type: str = ""
    total_bytes: int = 0
    free_bytes: int = 0
    device: str = ""
    ok: bool = False                # 能否直接作为录像存储目标
    reason: str = ""                # 不可用的原因（中文）
    is_current: bool = False

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "label": self.label,
            "kind": self.kind,
            "mounted": self.mounted,
            "writable": self.writable,
            "removable": self.removable,
            "fs_type": self.fs_type,
            "total_bytes": self.total_bytes,
            "free_bytes": self.free_bytes,
            "total_human": _human(self.total_bytes),
            "free_human": _human(self.free_bytes),
            "device": self.device,
            "ok": self.ok,
            "reason": self.reason,
            "is_current": self.is_current,
        }


# ----------------------------------------------------------------------
# 探测
# ----------------------------------------------------------------------
def probe(path: str | Path, *, internal: bool = False,
          current: str = "") -> StorageInfo:
    """采集单个路径的存储状态。

    `internal=True` 表示这是内部存储（应用目录下的 media/），
    不要求它是挂载点。
    """
    p = Path(path).expanduser()
    mounts = _read_mounts()
    spath = str(p)

    info = StorageInfo(path=spath)
    info.mounted = spath in mounts
    if info.mounted:
        info.device, info.fs_type = mounts[spath]
    else:
        # 落在某个已挂载点的子目录上时，继承父挂载点的设备信息
        for mount in sorted(mounts, key=len, reverse=True):
            if spath.startswith(mount.rstrip("/") + "/"):
                info.device, info.fs_type = mounts[mount]
                break
    info.removable = _is_removable(info.device)

    if p.exists():
        total, free = _space(p)
        info.total_bytes, info.free_bytes = total, free
        info.writable = _really_writable(p)
    else:
        info.writable = False

    # 分类
    if internal:
        info.kind = "internal"
        info.label = "内置存储（SD 卡）"
    elif info.removable:
        if info.fs_type.startswith("vfat") or "mmcblk" in info.device:
            info.kind = "sdcard"
        else:
            info.kind = "usb"
        info.label = p.name or spath
    else:
        info.kind = "external"
        info.label = p.name or spath

    if not p.exists():
        info.ok = False
        info.reason = "路径不存在"
    elif not info.mounted and not internal:
        info.ok = False
        info.reason = "当前未挂载（设备已拔出或未识别）"
    elif info.mounted and spath in mounts:
        dev_mount = mounts[spath][0]
        # 根文件系统必须排在"可写"之前判断：根目录对普通用户天然不可写，
        # 先判权限会给出"没有写入权限"这种让人摸不着头脑的原因。
        if dev_mount.startswith("/dev/") and _is_root_device(dev_mount):
            info.ok = False
            info.reason = "指向根文件系统，无法作为外部存储"
        elif not info.writable:
            info.ok = False
            info.reason = "不可写"
        else:
            info.ok = True
    elif not info.writable:
        info.ok = False
        info.reason = "不可写"
    else:
        info.ok = True

    if info.ok and info.free_bytes and info.free_bytes < 64 * 1024 * 1024:
        info.ok = False
        info.reason = "剩余空间不足 64MB"

    info.is_current = bool(current) and spath == str(current)
    return info


def _is_root_device(device: str) -> bool:
    """设备是否是根文件系统所在的那块盘。

    复用 :func:`_read_mounts` 而不是自己再读一遍 /proc/mounts：
    挂载表只应有一个读取入口，否则测试替身和真实实现会走偏。
    """
    root = _read_mounts().get(_ROOT_FS)
    return bool(root) and root[0] == device


def enumerate_devices(internal_path: str = "", current: str = "") -> list[StorageInfo]:
    """列出所有候选存储位置：内部存储 + 扫描到的可移动设备。"""
    seen: dict[str, StorageInfo] = {}

    if internal_path:
        info = probe(internal_path, internal=True, current=current)
        seen[info.path] = info

    mounts = _read_mounts()
    candidates: set[str] = set()
    for root in _SCAN_ROOTS:
        rp = Path(root)
        if not rp.is_dir():
            continue
        try:
            for child in rp.iterdir():
                candidates.add(str(child))
                if child.is_dir():
                    try:
                        for sub in child.iterdir():
                            candidates.add(str(sub))
                    except OSError:
                        pass
        except OSError:
            continue
    candidates.update(_SCAN_SINGLE)
    # 挂载点里出现过的、位于扫描根目录下的也一并纳入
    for mount in mounts:
        for root in _SCAN_ROOTS:
            if mount == root or mount.startswith(root.rstrip("/") + "/"):
                candidates.add(mount)
                break

    for path in sorted(candidates):
        if path in seen:
            continue
        p = Path(path)
        if not p.is_dir():
            continue
        info = probe(path, current=current)
        if info.mounted or info.removable:
            seen[path] = info

    # 当前配置指向的目录即使没被扫描到，也要出现在列表里
    if current and current not in seen:
        seen[current] = probe(current, current=current)

    return list(seen.values())


# ----------------------------------------------------------------------
# 目标校验
# ----------------------------------------------------------------------
def check_target(path: str, *, require_mount: bool = True,
                 internal_path: str = "", min_free_bytes: int = 0) -> tuple[bool, str]:
    """校验 `path` 能否作为录像存储目标。

    返回 (是否通过, 中文原因)。
    """
    raw = (path or "").strip()
    if not raw:
        return True, "使用内置存储"

    p = Path(raw).expanduser()
    if not p.is_absolute():
        return False, "必须使用绝对路径"

    if internal_path and str(p) == str(Path(internal_path).expanduser()):
        return True, "使用内置存储"

    mounts = _read_mounts()
    spath = str(p)

    if not p.exists():
        # 路径不存在时，只有在它正好是某个挂载点时才允许
        if spath in mounts:
            pass
        else:
            return False, "路径不存在"

    if require_mount and spath not in mounts:
        return False, ("该路径当前不是挂载点，设备可能未插入或已被拔出；"
                       "如果想直接用某个普通目录，请关闭“必须是挂载点”")

    # 根文件系统检查要排在权限检查之前：根目录对普通用户天然不可写，
    # 先判权限只会给出"没有写入权限"这种误导性的原因。
    if spath in mounts:
        device = mounts[spath][0]
        if device.startswith("/dev/") and _is_root_device(device):
            return False, "指向根文件系统，无法作为外部存储"

    if not os.access(str(p), os.W_OK):
        return False, "没有写入权限"

    if not _really_writable(p):
        return False, "实际写入测试失败"

    total, free = _space(p)
    if min_free_bytes and free < min_free_bytes:
        return False, f"剩余空间不足 {_human(free)}（至少需要 {_human(min_free_bytes)}）"

    return True, "可用"


def disk_usage(path: str | Path) -> tuple[int, int]:
    """返回 (总字节, 可用字节)。"""
    return _space(Path(path).expanduser())


# ----------------------------------------------------------------------
# 实时校验（写媒体前调用）
# ----------------------------------------------------------------------
def live_check(config) -> tuple[bool, str, Path]:
    """校验配置中的媒体目录**此刻**能否写入。

    返回 (是否可写, 原因, 应当写入的目录)。

    与 :func:`check_target` 的区别：这里读的是运行中的 ``Config``，
    会自动遵守 ``media.require_mount`` / ``media.fallback_internal``
    两个开关，并决定"外部存储不可用时回退到内置存储还是直接拒绝"。
    """
    internal = config.internal_media_dir()
    target = config.media_dir_configured()

    if str(target) == str(internal):
        return True, "", internal

    require_mount = bool(config.get("media", "require_mount", default=True))
    ok, reason = check_target(str(target), require_mount=require_mount,
                              internal_path=str(internal))
    if ok:
        return True, "", target
    if bool(config.get("media", "fallback_internal", default=False)):
        return True, reason, internal
    return False, reason, target


# ----------------------------------------------------------------------
# 后台监视器
# ----------------------------------------------------------------------
class StorageMonitor:
    """持续校验媒体存储目标，拔盘时及时报警或回退。

    每 ``interval`` 秒做一次实时校验，并把结果写进 ``Config`` 的运行时
    状态与 ``RuntimeState``，供界面显示与录像写入前拦截使用。
    """

    def __init__(self, config, state, log=None, interval: float = 3.0,
                 on_disk=None):
        self.config = config
        self.state = state
        self.log = log
        self.interval = max(1.0, float(interval))
        # 每轮复查时顺带刷新磁盘剩余空间（轻量，不遍历媒体目录）
        self.on_disk = on_disk
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._last_key = ""

    # -- 生命周期 -------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="storage-monitor",
                                        daemon=True)
        self._thread.start()
        self.tick()

    def stop(self) -> None:
        self._stop.set()
        th = self._thread
        if th and th.is_alive():
            th.join(timeout=2.0)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001
                self._log(f"storage monitor error: {exc}")

    def _log(self, msg: str) -> None:
        if self.log:
            try:
                self.log(msg)
            except Exception:
                pass

    # -- 校验 -----------------------------------------------------------
    def tick(self) -> dict:
        """做一次实时校验并同步状态，返回本次结果。"""
        ok, reason, target = live_check(self.config)
        configured = self.config.media_dir_configured()
        fallback = ok and str(target) != str(configured)

        self.config.set_media_runtime(
            directory=target, available=ok, reason=reason,
            fallback=fallback, target=str(configured),
        )

        key = f"{ok}|{fallback}|{reason}|{target}"
        with self._lock:
            changed = key != self._last_key
            self._last_key = key

        if changed:
            if ok and not fallback:
                self._log(f"storage target ok: {target}")
            elif fallback:
                self._log(f"storage target unavailable ({reason}); "
                          f"fallback to {target}")
            else:
                self._log(f"storage target unavailable: {reason}")

        try:
            self.state.update(
                storage_available=ok,
                storage_fallback=fallback,
                storage_path=str(target),
                storage_reason=reason,
            )
        except Exception:
            pass

        # 目标变了（切换了外部存储、或从回退状态切回），磁盘剩余空间
        # 必须按**新目标**重算，不能沿用旧目标的数值。
        if self.on_disk:
            try:
                self.on_disk()
            except Exception as exc:  # noqa: BLE001
                self._log(f"disk check error: {exc}")
        return {"ok": ok, "reason": reason, "dir": str(target),
                "fallback": fallback, "target": str(configured)}

    # -- 对外状态 -------------------------------------------------------
    def status(self) -> dict:
        """给 /api/storage 用的完整状态。"""
        st = self.config.media_status()
        try:
            devices = enumerate_devices(
                internal_path=str(self.config.internal_media_dir()),
                current=str(self.config.media_dir_configured()),
            )
        except Exception:
            devices = []
        st["devices"] = [d.to_dict() for d in devices]
        total, free = disk_usage(self.config.media_dir())
        st["usage"] = {"total": total, "free": free,
                       "total_human": _human(total), "free_human": _human(free)}
        # 磁盘护栏状态：剩余空间是否已经低于下限
        try:
            st["disk_low"] = bool(self.state.get("disk_low", False))
            st["disk_reason"] = self.state.get("disk_reason", "") or ""
            st["min_free_gb"] = float(
                self.config.get("record", "min_free_gb", default=1) or 0)
        except Exception:
            pass
        return st

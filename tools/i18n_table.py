"""i18n 对照表：源码中文 -> (i18n key, 英文译文)。

`tools/apply_i18n.py` 用它做三件事：
  1. 把 `templates/*.html` 里的静态文案打上 `data-i18n` 标记；
  2. 把 `static/app.js` 里的中文文案替换成 `t('key')` 调用；
  3. 生成 `core/locales/zh-CN.json` 与 `core/locales/en-US.json`。

键名规则：`<域>.<语义>`，例如 `nav.preview` / `btn.refresh` / `toast.regionSaved`。
表里带 `{占位符}` 的条目是"整句模板"，供迁移脚本手工替换拼接语句时使用。
"""

# 原文 -> (key, English)
T = {
    # ---------------- 应用 / 顶栏 ----------------
    "移动侦测录像控制台": ("app.console", "Motion Detection Recording Console"),
    "pikrellcam-lite · 移动侦测录像": ("app.title", "pikrellcam-lite · Motion Detection Recording"),
    "pikrellcam-lite · 登录": ("app.titleLogin", "pikrellcam-lite · Sign in"),
    "连接中…": ("status.connecting", "Connecting…"),
    "侦测 FPS": ("metric.detectFps", "Detect FPS"),
    "事件": ("metric.events", "Events"),
    "磁盘": ("metric.disk", "Disk"),
    "预设": ("metric.preset", "Preset"),
    "退出登录": ("btn.logout", "Log out"),
    "刷新": ("btn.refresh", "Refresh"),
    "每秒刷新": ("log.autoRefresh", "Refresh every second"),
    "清屏": ("btn.clearScreen", "Clear"),
    "需要登录": ("err.loginRequired", "Sign-in required"),
    "登录": ("btn.login", "Sign in"),
    "请输入访问密码以继续": ("login.prompt", "Enter the access password to continue"),
    "访问密码": ("login.password", "Access password"),
    "无法连接服务": ("err.cannotConnect", "Cannot reach the service"),
    "密码错误": ("err.badPassword", "Wrong password"),

    # ---------------- 导航 ----------------
    "实时预览": ("nav.preview", "Live Preview"),
    "侦测调参": ("nav.detect", "Detection Tuning"),
    "媒体": ("nav.media", "Media"),
    "定时命令": ("nav.schedule", "Scheduled Commands"),
    "舵机": ("nav.servo", "Servo"),
    "系统": ("nav.system", "System"),

    # ---------------- 预览页 ----------------
    "实时画面": ("panel.liveView", "Live View"),
    "选择摄像头": ("cam.pickTitle", "Select webcam"),
    "自动选择": ("cam.auto", "Auto select"),
    "选择采集通路": ("cam.pickPath", "Select capture path"),
    "自动通路": ("cam.autoPath", "Auto path"),
    "ISP 硬件 JPEG": ("cam.pathMjpeg", "ISP hardware JPEG"),
    "原始 RGB": ("cam.pathRgb", "Raw RGB"),
    "采集通路：CSI 走 ISP 硬件 JPEG 或原始 RGB": (
        "cam.pathHint", "Capture path: ISP hardware JPEG or raw RGB on CSI"),
    "切换到所选摄像头": ("cam.switchTo", "Switch to the selected webcam"),
    "切换": ("btn.switch", "Switch"),
    "拖拽画面可绘制检测区域": ("hint.dragRegions", "Drag on the image to draw detection regions"),
    "静止": ("state.still", "Still"),
    "侦测到移动": ("state.motion", "Motion detected"),
    "暂停侦测": ("btn.pauseDetect", "Pause detection"),
    "启用侦测": ("btn.enableDetect", "Enable detection"),
    "恢复录像": ("btn.resumeRecord", "Resume recording"),
    "暂停录像": ("btn.pauseRecord", "Pause recording"),
    "抓拍一张": ("btn.snapshot", "Take a snapshot"),
    "重启服务": ("btn.restartService", "Restart service"),
    "服务未运行": ("state.serviceStopped", "Service not running"),
    "相机未就绪": ("state.cameraNotReady", "Camera not ready"),
    "运行中": ("state.running", "Running"),
    "未选择": ("state.notSelected", "Not selected"),
    "错误：": ("err.prefix", "Error: "),
    "视频流不可用（相机未就绪？）": ("err.noStream", "Video stream unavailable (camera not ready?)"),
    "未启用密码保护": ("pwd.disabled", "Password protection is off"),
    "已启用密码保护": ("pwd.enabled", "Password protection is on"),
    "已关闭密码保护": ("pwd.turnedOff", "Password protection disabled"),
    "密码已设置": ("pwd.set", "Password set"),
    "密码保护已关闭": ("pwd.protectionOff", "Password protection is off"),
    "设置失败：": ("err.setFailed", "Failed to set: "),
    "新访问密码（留空则关闭密码保护）": (
        "pwd.newPlaceholder", "New access password (leave empty to disable password protection)"),

    # ---------------- 运动区域 ----------------
    "运动区域": ("panel.regions", "Motion Regions"),
    "保存区域": ("btn.saveRegions", "Save regions"),
    "新增整屏区域": ("btn.addFullRegion", "Add full-screen region"),
    "新区域名称": ("region.newName", "New region name"),
    "输入名称": ("region.inputName", "Enter a name"),
    "重命名区域": ("region.renameTitle", "Rename region"),
    "给这个检测区域起个名字。": ("region.renameText", "Give this detection region a name."),
    "保存": ("btn.save", "Save"),
    "区域": ("region.defaultName", "Region"),
    "区域已保存（": ("toast.regionSavedPrefix", "Regions saved ("),
    "个）": ("toast.regionSavedSuffix", ")"),
    "保存区域失败：": ("err.saveRegions", "Failed to save regions: "),
    "区域数量已达上限 32": ("err.regionLimit", "Maximum of 32 regions reached"),
    "已新增区域，可在右侧重命名": ("toast.regionAdded", "Region added — rename it on the right"),
    "区域预设": ("panel.regionPresets", "Region Presets"),
    "保存当前为预设": ("btn.saveAsRegionPreset", "Save current as preset"),
    "载入": ("btn.load", "Load"),
    "区域预设已保存": ("toast.regionPresetSaved", "Region preset saved"),
    "保存失败：": ("err.saveFailed", "Failed to save: "),
    "请输入预设名称": ("err.presetNameRequired", "Please enter a preset name"),
    "请先选择预设": ("err.selectPresetFirst", "Please select a preset first"),
    "载入失败：": ("err.loadFailed", "Failed to load: "),

    # ---------------- 侦测算法 ----------------
    "far / near 并行": ("algo.parallel", "far / near in parallel"),
    "远处小而慢的目标": ("algo.farDesc", "Small and slow targets in the distance"),
    "近处大而快的目标": ("algo.nearDesc", "Large and fast targets up close"),
    "far 算法面向远处小而慢的目标，near 算法面向近处大目标；两者可同时开启，也可只用一个。": (
        "algo.intro",
        "The far algorithm targets small, slow objects in the distance; the near algorithm "
        "targets large objects up close. Enable both, or just one."),
    "幅度阈值": ("algo.magnitude", "Magnitude threshold"),
    "单像素灰度差下限，越大越迟钝": (
        "algo.magnitudeDesc", "Minimum per-pixel grayscale difference — larger is less sensitive"),
    "占比阈值": ("algo.count", "Density threshold"),
    "区域内变化像素占比超过该值即命中": (
        "algo.countDesc", "A region is hit once the share of changed pixels exceeds this value"),
    "连续帧": ("algo.consecutive", "Consecutive frames"),
    "帧": ("algo.framesUnit", "frames"),
    "连续命中多少帧才判定为移动": (
        "algo.consecutiveDesc", "How many consecutive hits are needed to report motion"),
    "去噪半径": ("algo.noise", "Noise filter radius"),
    "关闭": ("algo.off", "off"),
    "邻域去噪半径，过滤孤立噪点（0 关闭）": (
        "algo.noiseDesc", "Neighbourhood denoise radius that filters isolated noise (0 disables it)"),
    "启用": ("common.enabled", "Enabled"),
    "停用": ("common.disabled", "Disabled"),
    "保存算法参数失败：": ("err.saveAlgo", "Failed to save algorithm settings: "),

    # ---------------- 录像 / 延时 / 预设 ----------------
    "录像参数": ("panel.recordParams", "Recording Parameters"),
    "编码器": ("label.encoder", "Encoder"),
    "分辨率/帧率变更会重启采集": ("hint.restartOnChange", "Changing resolution or frame rate restarts capture"),
    "主码流分辨率": ("label.mainResolution", "Main stream resolution"),
    "镜像": ("label.flip", "Mirror"),
    "侦测分辨率": ("label.detectResolution", "Detection resolution"),
    "延时摄影参数": ("panel.timelapseParams", "Timelapse Parameters"),
    "保存配置": ("btn.saveConfig", "Save settings"),
    "恢复默认配置": ("btn.resetConfig", "Restore defaults"),
    "所有配置项将恢复默认值，确定继续？": (
        "confirm.resetConfig", "All settings will be restored to defaults. Continue?"),
    "恢复": ("btn.restore", "Restore"),
    "已恢复默认配置": ("toast.configReset", "Default settings restored"),
    "恢复失败：": ("err.resetFailed", "Failed to restore: "),
    "配置已保存": ("toast.configSaved", "Settings saved"),
    "保存配置失败：": ("err.saveConfig", "Failed to save settings: "),
    "保存当前配置为预设": ("btn.saveConfigAsPreset", "Save current settings as preset"),
    "新预设名称": ("preset.newName", "New preset name"),
    "预设名称": ("preset.name", "Preset name"),
    "个区域": ("preset.regionCount", "regions"),
    "个配置段": ("preset.sectionCount", "sections"),
    "删除预设": ("preset.deleteTitle", "Delete preset"),
    "删除": ("btn.delete", "Delete"),
    "预设已删除": ("toast.presetDeleted", "Preset deleted"),
    "删除失败：": ("err.deleteFailed", "Failed to delete: "),
    "预设已保存": ("toast.presetSaved", "Preset saved"),
    "保存预设失败：": ("err.savePreset", "Failed to save preset: "),
    "（暂无预设）": ("preset.noneOption", "(no presets)"),
    "还没有预设。保存当前配置后可一键切换。": (
        "preset.empty", "No presets yet. Save the current settings to switch with one click."),

    # ---------------- 媒体 / 事件 ----------------
    "录像与抓拍": ("panel.media", "Recordings & Snapshots"),
    "录像": ("label.videos", "Recordings"),
    "抓拍": ("label.stills", "Snapshots"),
    "清空录像": ("btn.purgeVideos", "Delete all recordings"),
    "清空抓拍": ("btn.purgeStills", "Delete all snapshots"),
    "全部清空": ("btn.purgeAll", "Delete everything"),
    "清空": ("btn.purge", "Delete all"),
    "确定删除全部": ("confirm.purgeAll", "Delete all"),
    "？该操作不可恢复。": ("confirm.irreversible", "? This cannot be undone."),
    "已清理 ": ("toast.purgedPrefix", "Removed "),
    "个文件": ("toast.purgedSuffix", "files"),
    "清理失败：": ("err.purgeFailed", "Failed to clean up: "),
    "还没有事件录像。": ("media.noEvents", "No event recordings yet."),
    "缩略图": ("thumb.alt", "Thumbnail"),
    "目标裁剪": ("thumb.cropAlt", "Motion crop"),
    "· 时长": ("event.duration", "· duration"),
    "· 帧": ("event.frames", "· frames"),
    "算法": ("event.algorithm", "Algorithm"),
    "· 区域": ("event.region", "· region"),
    "· 编码": ("event.codec", "· codec"),
    "播放": ("btn.play", "Play"),
    "下载": ("btn.download", "Download"),
    "查看": ("btn.view", "View"),
    "归档到远端": ("btn.archive", "Archive to remote"),
    "已归档到 ": ("toast.archivedTo", "Archived to "),
    "远端": ("common.remote", "remote"),
    "归档失败：": ("err.archiveFailed", "Failed to archive: "),
    "删除事件": ("event.deleteTitle", "Delete event"),
    "事件已删除": ("toast.eventDeleted", "Event deleted"),
    "事件列表加载失败：": ("err.eventsLoadFailed", "Failed to load the event list: "),
    "暂无文件。": ("media.noFiles", "No files."),
    "列表加载失败：": ("err.listLoadFailed", "Failed to load the list: "),
    "暂无检测区域，画面上拖拽即可创建。": (
        "region.empty", "No detection regions yet — drag on the image to create one."),
    "还没有区域预设。画好区域后在上方命名保存。": (
        "regionPreset.empty", "No region presets yet. Draw a region and name it above to save."),
    "还没有位置预设，可用上方“保存为位置预设”。": (
        "servo.noPositionPresets", "No position presets yet. Use \"Save as position preset\" above."),

    # ---------------- 延时摄影 ----------------
    "未运行": ("tl.notRunning", "Not running"),
    "开始": ("btn.start", "Start"),
    "保持": ("btn.hold", "Hold"),
    "结束并合成": ("btn.finish", "End & merge"),
    "结束延时摄影": ("btn.endTimelapse", "End timelapse"),
    "结束并合成延时视频？": ("confirm.endTimelapse", "End and merge the timelapse video?"),
    "结束": ("btn.end", "End"),
    "延时摄影已开始（周期 ": ("toast.tlStarted", "Timelapse started (period "),
    "s）": ("toast.tlStartedSuffix", "s)"),
    "启动失败：": ("err.startFailed", "Failed to start: "),
    "操作失败：": ("err.opFailed", "Operation failed: "),
    "延时摄影已结束": ("toast.tlEnded", "Timelapse finished"),
    "结束失败：": ("err.endFailed", "Failed to finish: "),
    "取消保持": ("btn.cancelHold", "Cancel hold"),
    "运行中（保持）": ("tl.runningHold", "Running (holding)"),
    "周期": ("tl.period", "Period"),
    "s · 已拍": ("tl.taken", "s · captured"),
    "张": ("tl.shots", "shots"),
    "· 会话": ("tl.session", "· session"),

    # ---------------- 定时命令 ----------------
    "新增 / 编辑定时命令": ("panel.scheduleEditor", "Add / Edit Scheduled Command"),
    "星期": ("label.weekday", "Weekday"),
    "时刻": ("label.time", "Time"),
    "时刻/间隔": ("label.timeOrInterval", "Time / Interval"),
    "间隔(分钟, &gt;0 时优先)": ("label.interval", "Interval (minutes, takes priority when &gt; 0)"),
    "命令": ("label.command", "Command"),
    "保存命令": ("btn.saveCommand", "Save command"),
    "清空表单": ("btn.clearForm", "Clear form"),
    "servo goto 名称": ("label.servoGoto", "servo goto name"),
    "重新载入": ("btn.reload", "Reload"),
    "立即执行": ("btn.runNow", "Run now"),
    "启用": ("common.enable", "Enable"),
    "编辑": ("btn.edit", "Edit"),
    "暂无定时命令。": ("sched.empty", "No scheduled commands."),
    "加载失败：": ("err.schedLoadFailed", "Failed to load: "),
    "命令不能为空": ("err.cmdEmpty", "The command cannot be empty"),
    "定时命令已保存": ("toast.schedSaved", "Scheduled command saved"),
    "正在编辑第 ": ("sched.editingPrefix", "Editing command #"),
    "条，保存后覆盖": ("sched.editingSuffix", " — saving will overwrite it"),
    "删除定时命令": ("sched.deleteTitle", "Delete scheduled command"),
    "确定删除第 ": ("confirm.deleteSchedPrefix", "Delete command #"),
    "条命令？": ("confirm.deleteSchedSuffix", "?"),
    "已删除": ("toast.deleted", "Deleted"),
    "（无输出）": ("cmd.noOutput", "(no output)"),
    "命令已执行": ("toast.cmdExecuted", "Command executed"),
    "执行失败：": ("err.execFailed", "Failed to execute: "),
    "请输入命令": ("err.cmdRequired", "Please enter a command"),
    "命令表已重新载入": ("toast.schedReloaded", "Command list reloaded"),
    "每 ": ("sched.everyPrefix", "Every "),
    "分钟": ("sched.everySuffix", "minutes"),

    # ---------------- 舵机 ----------------
    "启用舵机": ("btn.enableServo", "Enable servo"),
    "停用舵机": ("btn.disableServo", "Disable servo"),
    "手动控制": ("panel.manualControl", "Manual Control"),
    "转到该位置": ("btn.gotoPosition", "Go to position"),
    "保存为位置预设": ("btn.savePosition", "Save as position preset"),
    "位置名称": ("servo.positionName", "Position name"),
    "请输入位置名称": ("err.positionNameRequired", "Please enter a position name"),
    "位置预设已保存": ("toast.positionSaved", "Position preset saved"),
    "舵机已启用": ("toast.servoEnabled", "Servo enabled"),
    "启用失败：": ("err.enableFailed", "Failed to enable: "),
    "舵机已停用": ("toast.servoDisabled", "Servo disabled"),
    "停用失败：": ("err.disableFailed", "Failed to disable: "),
    "舵机已转到指定位置": ("toast.servoMoved", "Servo moved to the requested position"),
    "转动失败：": ("err.moveFailed", "Failed to move: "),

    # ---------------- 服务 / 升级 / 钩子 ----------------
    "服务控制": ("panel.serviceControl", "Service Control"),
    "启动服务": ("btn.startService", "Start service"),
    "停止服务": ("btn.stopService", "Stop service"),
    "停止后画面与侦测将停止，恢复需重新启动服务。": (
        "hint.stopService", "After stopping, the picture and detection stop. Restart the service to resume."),
    "服务操作": ("panel.serviceAction", "Service action"),
    "启动": ("svc.start", "Start"),
    "停止": ("svc.stop", "Stop"),
    "重启": ("svc.restart", "Restart"),
    "服务？": ("confirm.serviceActionSuffix", " the service?"),
    "服务操作已执行": ("toast.serviceActionDone", "Service action executed"),
    "一键升级": ("btn.upgrade", "One-click upgrade"),
    "将从 git 远端拉取最新代码并重启服务，期间画面会短暂中断。确定继续？": (
        "confirm.upgrade",
        "The latest code will be pulled from the git remote and the service restarted; "
        "the picture will be interrupted briefly. Continue?"),
    "开始升级": ("btn.startUpgrade", "Start upgrade"),
    "升级中…": ("state.upgrading", "Upgrading…"),
    "升级完成": ("toast.upgradeDone", "Upgrade complete"),
    "升级失败": ("toast.upgradeFailed", "Upgrade failed"),
    "升级失败：": ("err.upgradeFailed", "Upgrade failed: "),
    "升级与密码": ("panel.upgradePassword", "Upgrade & Password"),
    "保存密码": ("btn.savePassword", "Save password"),
    "检测中…": ("state.detecting", "Detecting…"),
    "版本与发布": ("panel.versionRelease", "Version & Release"),
    "事件钩子": ("panel.eventHooks", "Event Hooks"),
    "移动开始 (on_motion_begin)": ("hook.onMotionBegin", "Motion start (on_motion_begin)"),
    "移动结束 (on_motion_end)": ("hook.onMotionEnd", "Motion end (on_motion_end)"),
    "预览保存 (on_motion_preview_save)": ("hook.onPreviewSave", "Preview saved (on_motion_preview_save)"),
    "延时结束 (on_timelapse_end)": ("hook.onTimelapseEnd", "Timelapse end (on_timelapse_end)"),
    "保存钩子": ("btn.saveHooks", "Save hooks"),
    "钩子已保存": ("toast.hooksSaved", "Hooks saved"),
    "钩子配置已保存": ("toast.hookConfigSaved", "Hook configuration saved"),
    "系统信息": ("panel.systemInfo", "System Information"),
    "帮助说明": ("panel.help", "Help"),
    "确定": ("btn.ok", "OK"),
    "取消": ("btn.cancel", "Cancel"),
    "确认": ("btn.confirm", "Confirm"),
    "服务已重启": ("toast.serviceRestarted", "Service restarted"),
    "确定重启服务？画面会短暂中断。": ("confirm.restart", "Restart the service? The picture will be interrupted briefly."),
    "重启失败：": ("err.restartFailed", "Failed to restart: "),
    "已抓拍：": ("toast.snapshotSaved", "Snapshot saved: "),
    "抓拍失败：": ("err.snapshotFailed", "Failed to take the snapshot: "),
    "已暂停侦测": ("toast.detectPaused", "Detection paused"),
    "已启用侦测": ("toast.detectEnabled", "Detection enabled"),
    "已恢复录像": ("toast.recordResumed", "Recording resumed"),
    "已暂停录像": ("toast.recordPaused", "Recording paused"),

    # ---------------- 摄像头面板 ----------------
    "正在读取摄像头…": ("cam.loading", "Reading webcams…"),
    "共发现 ": ("cam.foundPrefix", "Found "),
    "个摄像头，当前使用：": ("cam.foundSuffix", " webcam(s), currently using: "),
    "未发现摄像头": ("cam.noneFound", "No webcam found"),
    "读取摄像头列表失败：": ("err.camListFailed", "Failed to read the webcam list: "),
    "正在切换摄像头…": ("cam.switching", "Switching webcam…"),
    "切换失败：": ("err.switchFailed", "Failed to switch: "),
    "刷新列表": ("btn.refreshList", "Refresh list"),
    "未知设备": ("cam.unknown", "Unknown device"),

    # ---------------- 详情字段 ----------------
    "后端": ("detail.backend", "Backend"),
    "状态": ("detail.status", "Status"),
    "类型": ("detail.type", "Type"),
    "设备": ("detail.device", "Device"),
    "型号": ("detail.model", "Model"),
    "格式": ("detail.format", "Format"),
    "分辨率": ("detail.resolution", "Resolution"),
    "主机名": ("detail.hostname", "Hostname"),
    "平台": ("detail.platform", "Platform"),
    "程序目录": ("detail.appDir", "Program directory"),
    "媒体目录": ("detail.mediaDir", "Media directory"),
    "运行时间": ("detail.uptime", "Uptime"),
    "当前版本": ("detail.currentVersion", "Current version"),
    "发布目录": ("detail.releaseDir", "Release directory"),
    "已保留版本": ("detail.keptVersions", "Retained versions"),
    "共享根目录": ("detail.sharedRoot", "Shared root directory"),
    "当前 Pan": ("detail.currentPan", "Current Pan"),
    "当前 Tilt": ("detail.currentTilt", "Current Tilt"),
    "Pan 限位": ("detail.panLimits", "Pan limits"),
    "Tilt 限位": ("detail.tiltLimits", "Tilt limits"),

    # ---------------- 其它 ----------------
    "操作": ("th.action", "Action"),
    "自动": ("common.auto", "Auto"),
    "曝光": ("label.exposure", "Exposure"),
    "旋转": ("label.rotation", "Rotation"),
    "帧率": ("label.fps", "Frame rate"),
    "侦测帧率": ("label.detectFps", "Detection frame rate"),
    "预录(秒)": ("label.preSeconds", "Pre-record (s)"),
    "补录(秒)": ("label.postSeconds", "Post-record (s)"),
    "事件间隔(秒)": ("label.eventGap", "Event gap (s)"),
    "单事件最长(秒)": ("label.maxEvent", "Max event length (s)"),
    "磁盘上限(GB)": ("label.maxDisk", "Disk limit (GB)"),
    "默认周期(秒)": ("label.tlPeriod", "Default period (s)"),
    "编码质量 CRF": ("label.crf", "Encoder quality CRF"),
    "启动后立即保持": ("label.tlHold", "Keep running after start"),
    "启用移动侦测": ("label.motionEnabled", "Enable motion detection"),
    "启动即开始侦测": ("label.startupMotion", "Start detecting on boot"),
    "启用延时摄影": ("label.tlEnabled", "Enable timelapse"),
    "例如：record on": ("ph.exampleRecord", "e.g. record on"),
    "例如：echo {id} &gt;&gt; /tmp/motion.log": (
        "ph.exampleHook", "e.g. echo {id} &gt;&gt; /tmp/motion.log"),
    "* 或 Mon-Fri 或 Mon,Wed": ("ph.weekday", "* or Mon-Fri or Mon,Wed"),
    "record on / tl_start 30 / servo goto 中": (
        "ph.commandExamples", "record on / tl_start 30 / servo goto <name>"),

    # ---------------- 整句模板（含占位符） ----------------
    "区域已保存（{n} 个）": ("toast.regionSaved", "Regions saved ({n})"),
    "已清理 {n} 个文件": ("toast.purged", "Removed {n} file(s)"),
    "每 {n} 分钟": ("sched.every", "Every {n} minutes"),
    "正在编辑第 {n} 条，保存后覆盖": ("sched.editing", "Editing command #{n} — saving overwrites it"),
    "确定删除第 {n} 条命令？": ("confirm.deleteSched", "Delete command #{n}?"),
    "共发现 {n} 个摄像头，当前使用：": ("cam.foundUsing", "Found {n} webcam(s), currently using: "),
    "已转到「{n}」": ("servo.movedToName", "Moved to \"{n}\""),
    "已载入区域预设「{n}」": ("toast.regionPresetLoadedName", "Region preset \"{n}\" loaded"),
    "已激活预设「{n}」": ("toast.presetActivatedName", "Preset \"{n}\" activated"),
    "确定删除预设「{n}」？": ("confirm.deletePresetName", "Delete preset \"{n}\"?"),
    "确定删除事件「{n}」及其录像文件？": (
        "confirm.deleteEventName", "Delete event \"{n}\" and its recording files?"),
    "已抓拍：{n}": ("toast.snapshotSavedName", "Snapshot saved: {n}"),
    "延时摄影已开始（周期 {n}s）": ("toast.tlStartedPeriod", "Timelapse started (period {n}s)"),
    "确定{action}服务？": ("confirm.serviceAction", "{action} the service?"),
    "确定删除全部{what}？该操作不可恢复。": (
        "confirm.purgeWhat", "Delete all {what}? This cannot be undone."),
    "已归档到 {n}": ("toast.archivedToName", "Archived to {n}"),

    # ---------------- 补录：主控台标签页 / 面板标题 ----------------
    "CSI / USB 移动侦测录像 · v": (
        "app.subtitle", "CSI / USB Motion Detection Recording · v"),
    "侦测": ("osd.detect", "Detect"),
    "变化": ("osd.change", "Change"),
    "在左侧画面上按住鼠标拖动即可绘制矩形；在右侧列表中点击某个区域即选中它，"
    "选中后可拖动框体移动、右下角小块缩放，双击框体可重命名。": (
        "hint.drawRegionsLong",
        "Hold the left mouse button and drag on the image to draw a rectangle; "
        "click a region in the list on the right to select it — once selected you can "
        "drag the box, resize it from the small corner handle, and double-click it to rename."),
    "双算法灵敏度": ("algo.dualTitle", "Dual-algorithm sensitivity"),
    "侦测开关": ("panel.detectToggle", "Detection switch"),
    "触发前预录(秒)": ("label.preSecondsFull", "Trigger pre-record (s)"),
    "触发后补录(秒)": ("label.postSecondsFull", "Trigger post-record (s)"),
    "相机参数": ("panel.cameraParams", "Camera Parameters"),
    "配置预设": ("panel.configPresets", "Configuration Presets"),
    "延时摄影": ("panel.timelapse", "Timelapse"),
    "秒": ("label.seconds", "s"),
    "事件录像": ("panel.eventVideos", "Event Recordings"),
    "录像文件": ("panel.videoFiles", "Video Files"),
    "抓拍图片": ("panel.stillImages", "Snapshot Images"),
    "内部命令：": ("hint.internalCommands", "Internal commands: "),
    "；~/.pikrellcam/at-commands.conf 里的条目可写任意 shell 命令，网页命令框只接受内部命令。": ("hint.anyShell", "; entries in ~/.pikrellcam/at-commands.conf may be any shell command, while the web command box only accepts internal commands."),
    "命令列表": ("panel.commandList", "Command List"),
    "执行": ("btn.execute", "Execute"),
    "舵机状态": ("panel.servoStatus", "Servo Status"),
    "平滑时间(ms)": ("label.smoothMs", "Smooth time (ms)"),
    "位置预设": ("panel.positionPresets", "Position Presets"),
    "摄像头": ("panel.webcam", "Webcam"),
    "当前状态：": ("hint.currentState", "Current state: "),
    "每个版本都独立保留在": ("hint.releasesKept", "Every version is kept separately under"),
    "目录下，回滚只需把": ("hint.rollback", "— to roll back, point the"),
    "软链指回旧版本。": ("hint.symlinkBack", "symlink back to the old version."),
    "可用占位符：": ("hint.placeholders", "Available placeholders: "),
    "实时日志": ("panel.liveLog", "Live Log"),
    "自动滚动": ("label.autoScroll", "Auto-scroll"),

    # ---------------- 补录：仅后端使用的消息 ----------------
    "不支持的语言": ("err.unsupportedLang", "Unsupported language"),

    # ---------------- 补录：中文标点 ----------------
    "、": ("sep.list", ", "),
    "：": ("sep.colon", ": "),

    # ---------------- 补录：JS 动态文案 ----------------
    "重命名": ("btn.rename", "Rename"),
    "已保存": ("common.saved", "Saved"),
    "激活": ("btn.activate", "Activate"),
    "已启用": ("servo.tagEnabled", "Enabled"),
    "未启用": ("servo.tagDisabled", "Not enabled"),
    "当前": ("detail.currentWord", "Current"),
    "限位": ("detail.limitWord", "Limits"),
}


# ----------------------------------------------------------------------
# 整句模板与「不来自源码抽取」的条目：key -> (中文, English)。
#
# 两类内容进这里：
#   1. 带 `{n}` 占位符的整句模板——中文语序和英文不同，不能靠切分拼出来；
#   2. 只在手工替换里出现、源码里已经不再保留原样的文案。
#
# EXTRA 会覆盖 T 里同名 key 的取值。
# ----------------------------------------------------------------------
EXTRA = {
    # --- 带占位符的整句模板 ---
    "preset.regionCount": ("{n} 个区域", "{n} region(s)"),
    "preset.sectionCount": ("{n} 个配置段", "{n} section(s)"),

    # --- 仅由手工替换使用 ---
    "label.mediaAll": ("录像与抓拍", "Recordings & Snapshots"),
    "detail.enabled": ("启用", "Enabled"),
    "detail.disabled": ("停用", "Disabled"),
    "err.loginFailed": ("登录失败", "Sign-in failed"),

    # --- 既有缺口：v2.6.0 的语言包里漏了这两条，界面上会直接显示 key ---
    "err.activateFailed": ("激活失败", "Failed to activate"),
    "btn.goto": ("转到", "Go to"),

    # --- 存储位置面板（v2.6.0 起）---
    # 这些 key 在 HTML / JS 里已写成 data-i18n / t('key') 的形式，
    # 不会被字面量扫描器收录，必须在这里登记，否则重新生成语言包时会丢。
    "panel.storage": ("存储位置", "Storage location"),
    "label.storageTarget": ("录像存储目标", "Recording storage target"),
    "label.storageFree": ("剩余空间", "Free space"),
    "label.storageRequireMount": ("目标必须是挂载点", "Target must be a mount point"),
    "label.storageFallback": ("设备拔出时回退到内置存储",
                              "Fall back to internal storage when the device is removed"),
    "btn.applyStorage": ("应用存储设置", "Apply storage settings"),
    "toast.storageSaved": ("存储设置已保存", "Storage settings saved"),
    "err.storageSaveFailed": ("保存存储设置失败：", "Failed to save storage settings: "),
    "hint.storageSafety": (
        "安全提示：默认在外部存储被拔出时暂停录像，而不是悄悄写回 SD 卡——"
        "否则长期运行会把系统分区撑满，设备无法启动。",
        "Safety: by default recording is paused when the external storage is removed "
        "instead of silently writing back to the SD card — otherwise long runs fill "
        "up the system partition and the device stops booting."),
    "storage.internal": ("内置存储", "Internal storage"),
    "storage.internalOption": ("内置存储（SD 卡）", "Internal storage (SD card)"),
    "storage.external": ("外部存储", "External storage"),
    "storage.usb": ("USB 存储", "USB storage"),
    "storage.sdcard": ("SD 卡", "SD card"),
    "storage.unknown": ("未知", "Unknown"),
    "storage.free": ("可用", "free"),
    "storage.usageLine": ("可用 {free} / 共 {total}", "usable {free} / {total} total"),
    "storage.ok": ("可用", "Available"),
    "storage.unavailable": ("不可用", "Unavailable"),
    "storage.fallback": ("已回退", "Fell back"),
    "storage.lowSpace": ("磁盘剩余空间不足", "Not enough free disk space"),
    "storage.noDevices": (
        "未检测到外部存储设备，插入 U 盘后点“刷新列表”。",
        "No external storage device detected. Plug in a USB drive and click “Refresh list”."),
    "storage.paused": ("存储不可用：{r}。录像已暂停。",
                       "Storage unavailable: {r}. Recording is paused."),
    "storage.fallbackNote": (
        "{r}。当前已回退到内置存储，外部存储恢复后会自动切回。",
        "{r}. Recording is using internal storage for now; it switches back "
        "automatically when the external storage returns."),

    # --- 磁盘监测（v2.6.1 起）---
    "metric.diskFree": ("剩余", "Free"),
    "label.minFree": ("剩余空间下限(GB)", "Free space floor (GB)"),
    "label.diskNow": (
        "媒体占用 {used} / 配额 {quota} · 磁盘剩余 {free} / 共 {total}",
        "Media {used} / quota {quota} · disk free {free} / {total}"),
    "hint.diskGuard": (
        "磁盘上限是媒体配额，可以调到 128 GB（比整块盘还大也没关系）；"
        "真正兜底的是剩余空间下限：低于它会自动清理最旧的录像，仍然不足则暂停录像。",
        "The disk limit is a media quota and may be set up to 128 GB (larger than the "
        "whole disk is fine). What really protects you is the free-space floor: "
        "below it the oldest recordings are removed automatically, and recording is "
        "paused if that is not enough."),

    # --- 成像参数矩阵（v2.7.0 起）---
    # 这些 key 在 HTML / JS 里已写成 data-i18n / t('key') 的形式，
    # 不会被字面量扫描器收录，必须在这里登记。
    "panel.imaging": ("成像参数", "Imaging"),
    "btn.saveImaging": ("应用成像参数", "Apply imaging"),
    "btn.resetImaging": ("恢复默认成像", "Reset imaging"),
    "toast.imagingSaved": ("成像参数已应用", "Imaging settings applied"),
    "toast.imagingReset": ("成像参数已恢复默认", "Imaging settings reset to defaults"),
    "err.saveImaging": ("保存成像参数失败：", "Failed to save imaging settings: "),
    "imaging.group.tone": ("影调", "Tone"),
    "imaging.group.exposure": ("曝光", "Exposure"),
    "imaging.group.color": ("色彩与变焦", "Colour & zoom"),
    "imaging.brightness": ("亮度", "Brightness"),
    "imaging.contrast": ("对比度", "Contrast"),
    "imaging.saturation": ("饱和度", "Saturation"),
    "imaging.sharpness": ("锐度", "Sharpness"),
    "imaging.denoise": ("降噪", "Noise reduction"),
    "imaging.exposure": ("曝光模式", "Exposure mode"),
    "imaging.metering": ("测光模式", "Metering"),
    "imaging.ev": ("曝光补偿", "Exposure compensation"),
    "imaging.iso": ("ISO 增益", "ISO gain"),
    "imaging.shutter": ("快门速度", "Shutter speed"),
    "imaging.awb": ("白平衡", "White balance"),
    "imaging.awbRGain": ("红色增益", "Red gain"),
    "imaging.awbBGain": ("蓝色增益", "Blue gain"),
    "imaging.zoom": ("数字变焦", "Digital zoom"),
    "imaging.denoiseAuto": ("自动", "Auto"),
    "imaging.denoiseOff": ("关闭", "Off"),
    "imaging.denoiseCdnOff": ("关闭（保留色彩降噪）", "Off (keep colour denoise)"),
    "imaging.denoiseCdnFast": ("快速", "Fast"),
    "imaging.denoiseCdnHq": ("高质量", "High quality"),
    "imaging.expNormal": ("标准", "Standard"),
    "imaging.expSport": ("运动（缩短曝光）", "Sport (short exposure)"),
    "imaging.meterCentre": ("中心", "Centre"),
    "imaging.meterSpot": ("点测光", "Spot"),
    "imaging.meterAverage": ("平均", "Average"),
    "imaging.meterCustom": ("自定义", "Custom"),
    "imaging.awbAuto": ("自动", "Auto"),
    "imaging.awbIncandescent": ("白炽灯", "Incandescent"),
    "imaging.awbTungsten": ("钨丝灯", "Tungsten"),
    "imaging.awbFluorescent": ("荧光灯", "Fluorescent"),
    "imaging.awbIndoor": ("室内", "Indoor"),
    "imaging.awbDaylight": ("日光", "Daylight"),
    "imaging.awbShade": ("阴影", "Shade"),
    "imaging.awbCloudy": ("阴天", "Cloudy"),
    "imaging.awbGreysworld": ("灰世界", "Greyscale world"),
    "imaging.backendRpicam": ("ISP 硬件通路", "ISP hardware path"),
    "imaging.backendLibcamera": ("libcamera 通路", "libcamera path"),
    "imaging.backendV4l2": ("USB 通路", "USB path"),
    "imaging.notSupported": ("当前采集通路不支持这一项", "Not supported by the current capture path"),
    "imaging.notApplied": (
        "这组成像参数没能被采集进程接受，已退回默认参数启动（详情见服务日志）。",
        "The capture process rejected these imaging settings and fell back to the "
        "defaults (see the service log for details)."),
    "imaging.unsupported": ("有 {n} 项在当前采集通路下不支持", "{n} setting(s) are not supported by the current capture path"),
    "hint.imagingBackend": (
        "不同采集通路支持的参数不一样：ISP 硬件通路的成像参数在采集进程启动时生效，"
        "改动会重启相机；libcamera 与 USB 通路可以热更新。",
        "Each capture path supports a different set of parameters: on the ISP hardware "
        "path the imaging settings are applied when the capture process starts, so a "
        "change restarts the camera; libcamera and USB apply them live."),
    "hint.imagingBrightness": ("整体画面明暗，50 为正常", "Overall brightness; 50 is normal"),
    "hint.imagingContrast": ("明暗对比强度，0 为正常", "Contrast strength; 0 is normal"),
    "hint.imagingSaturation": ("色彩浓度，0 为正常，-100 为纯黑白", "Colour intensity; 0 is normal, -100 is pure greyscale"),
    "hint.imagingSharpness": ("边缘锐化强度，0 为正常", "Edge sharpening; 0 is normal"),
    "hint.imagingDenoise": ("画面降噪，夜间噪点多时可以调高", "Noise reduction; useful in low light"),
    "hint.imagingExposure": ("曝光策略，运动会缩短曝光时间", "Exposure strategy; sport shortens the exposure"),
    "hint.imagingMetering": ("测光方式，决定自动曝光参考哪部分画面", "How auto exposure meters the scene"),
    "hint.imagingEv": ("自动曝光补偿档位，正数变亮、负数变暗", "Auto exposure compensation in stops"),
    "hint.imagingIso": ("固定 ISO 增益，0 为自动", "Fixed ISO gain; 0 means automatic"),
    "hint.imagingShutter": ("固定快门时间（微秒），0 为自动", "Fixed shutter time in microseconds; 0 means automatic"),
    "hint.imagingAwb": ("白平衡预设，夜间误色偏时选固定色温", "White balance preset; a fixed preset helps at night"),
    "hint.imagingAwbGains": ("手动设置红蓝通道增益，0 为自动", "Manual red/blue gain; 0 means automatic"),
    "hint.imagingZoom": ("数字变焦（裁剪画面放大），会损失分辨率", "Digital zoom (crops and enlarges); resolution is lost"),

    # --- 循环录像（v2.7.0 起）---
    "panel.loop": ("循环录像", "Loop recording"),
    "label.loopEnabled": ("启用循环录像", "Enable loop recording"),
    "label.loopSegment": ("每段时长(秒)", "Segment length (s)"),
    "label.loopPercent": ("占用磁盘上限(%)", "Disk usage cap (%)"),
    "label.loopQuality": ("编码质量 CRF", "Encoder quality CRF"),
    "btn.saveLoop": ("保存循环录像设置", "Save loop settings"),
    "btn.purgeLoop": ("清空循环录像", "Delete loop recordings"),
    "toast.loopSaved": ("循环录像设置已保存", "Loop settings saved"),
    "toast.loopPurged": ("循环录像已清空", "Loop recordings deleted"),
    "err.saveLoop": ("保存循环录像设置失败：", "Failed to save loop settings: "),
    "confirm.purgeLoop": (
        "确定要删除全部循环录像段吗？此操作不可撤销。",
        "Delete every loop recording segment? This cannot be undone."),
    "loop.disabled": ("未启用", "Disabled"),
    "loop.enabled": ("已启用", "Enabled"),
    "loop.recording": ("录制中", "Recording"),
    "loop.detail": ("{n} 段 · 占用 {size} / 上限 {limit}",
                    "{n} segment(s) · {size} used / {limit} cap"),
    "loop.paused": ("录像已暂停", "Recording paused"),
    "loop.pausedHint": ("录像已暂停，循环录像不会开始",
                        "Recording is paused, so loop recording will not start"),
    "loop.fps": ("实际 {fps} fps", "actual {fps} fps"),
    "hint.loopYield": (
        "循环录像与事件录像共用同一个硬件编码器，不能同时录："
        "检测到移动时循环录像会让位给事件录像，事件结束后自动恢复。"
        "占用超过上限时优先删除最旧的循环录像段，事件录像不受影响。",
        "Loop recording and event recording share the same hardware encoder and cannot "
        "run at the same time: when motion is detected the loop yields to the event "
        "clip and resumes afterwards. When the usage cap is exceeded the oldest loop "
        "segments are deleted first; event recordings are never touched."),
}


# ----------------------------------------------------------------------
# 帮助说明：后端 /api/help 的内容，按 key 编号取。
#
# 单独成表而不放进 T —— 因为「录像」「定时命令」「舵机」这些标题
# 在界面上已经有各自的 key，不能让帮助文案把它们覆盖掉。
# ----------------------------------------------------------------------
HELP = {
    "help.1.title": ('概览', 'Overview'),
    "help.1.body": ('pikrellcam-lite 是一个基于 libcamera/picamera2 的移动侦测录像服务，提供实时预览、运动检测录像、事件回看与网页调参。', 'pikrellcam-lite is a motion-detection recording service built on libcamera/picamera2. It provides live preview, motion-triggered recording, event playback and on-page tuning.'),
    "help.2.title": ('运动检测', 'Motion detection'),
    "help.2.body": ('使用帧差分实现双算法并行检测：far 算法面向远处小而慢的目标，near 算法面向近处大目标。可在多个运动区域上分别判定，区域可在网页预览图上拖拽绘制并命名保存。', 'Motion is detected with frame differencing running two algorithms in parallel: the far algorithm targets small, slow objects in the distance, the near algorithm targets large objects up close. Every motion region is judged independently, and regions can be drawn on the preview image and named for reuse.'),
    "help.3.title": ('录像', 'Recording'),
    "help.3.body": ('触发后先写入预录缓冲中的历史帧，再继续录制补录时长，结束后由 ffmpeg 统一编码为 H.264 MP4，并生成整帧缩略图与运动目标裁剪缩略图。', 'When motion triggers, the frames buffered by the pre-record window are written out first, recording then continues for the post-record duration, and the whole clip is finally encoded to H.264 MP4 by ffmpeg, together with a full-frame thumbnail and a cropped thumbnail of the moving object.'),
    "help.4.title": ('定时命令', 'Scheduled commands'),
    "help.4.body": ('可按星期+时刻或固定间隔执行命令。命令可以是内部命令（record on、tl_start 30 等）；也可以在 ~/.pikrellcam/at-commands.conf 里写任意 shell 命令，网页上的命令框只接受内部命令。', 'Commands can run on a weekday-and-time schedule or at a fixed interval. A command may be an internal command (record on, tl_start 30, ...), or any shell command when it is written in ~/.pikrellcam/at-commands.conf; the web command box only accepts internal commands.'),
    "help.5.title": ('舵机', 'Servo'),
    "help.5.body": ('支持 RPi.GPIO 或 ServoBlaster 驱动云台舵机，可保存位置预设并设置平移俯仰限位与平滑移动时间。', 'Pan-tilt servos are driven through RPi.GPIO or ServoBlaster. Position presets can be saved, and the pan/tilt travel limits plus a smoothing time can be configured.'),
    "help.6.title": ('运维', 'Operations'),
    "help.6.body": ('systemctl --user status pikrellcam-lite 查看状态；journalctl --user -u pikrellcam-lite -f 查看实时日志。', "Use 'systemctl --user status pikrellcam-lite' to check the service state and 'journalctl --user -u pikrellcam-lite -f' to follow the live log."),
}

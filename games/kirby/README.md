# 星之卡比 新星同盟（基础版）原生移植实验

目标 NSP 的 title ID 为 `01007E3006DDA000`，内部版本为 0。文件名中的 `4.1.0` 不是 NSP 内的更新版本。移植沿用项目的 ARM64 游戏代码直跑、Horizon 服务接管和 Metal NVN 后端；当前仍是开发预览，未通过完整游戏验收。

## 当前范围（2026-10-21）

| 功能 | 验证范围与限制 |
|---|---|
| 启动、影片画面、菜单、地图 | 已进入故事模式与前两个关卡入口；影片 PCM 音频尚未播放 |
| 移动、跳跃、存档 | 第一关与第二关做过基础操作，已验证重启读回进度；未完成全流程存档验证 |
| 基础 60 帧、原生 / MetalFX 2K | 第一关有实机截图与帧耗时记录；其他场景、长时间运行仍需回归 |
| UI 坐标 | 主菜单、返回世界选择确认框、暂停菜单已验证背景、边框、文字对齐 |
| MetalFX 补帧 | 四个模式已切换；采用整帧光流、平面深度和零相机运动，遮挡及文字可能重影 |
| 游戏语言 | 仅选择基础版已有的资源；当前简体中文环境回退英语，尚无中文资源 |

`build_app.py` 目前仍是 TOTK 构建入口。卡比没有从 NSP 到 App 的统一自动化命令；本目录保存适配补丁、SDK 补丁、预览打包器和测试。

## 已验证的进度

- ExeFS 和 RomFS 完整性验证通过；RomFS 共 4,442 个文件、3,080,511,292 字节。
- 三个游戏模块经重写后通过原生 PLT 探针，游戏进入 `nnMain`、初始化音频和 Metal，并向原生窗口持续提交帧。
- 实验宿主已接管开场 MP4 的 H.264 视频及 AAC 解码，能从 `avcc`/`esds` 参数解析配置、解出帧并交还给游戏。`audout` 缓冲区事件和释放队列已有最小实现，避免此前的崩溃；它尚未播放 PCM，因此音频仍是静音。
- 开场影片已在原生窗口显示运动画面。黑屏的直接原因是电影 YUV 转 RGB 的 64 字节矩阵为零；兼容补丁在最终 GPU uniform 绑定处提供有限范围 BT.709 矩阵，同时核对电影顶点程序及两张 NV12 纹理。原影片的色彩空间由 `ffprobe` 确认，实机截图位于外部宿主的 `analysis/movie-gpu-matrix-verified.png`。矩阵为何未由游戏初始化仍需继续追查。
- 已修复旧版 SDK 调试手柄和触摸屏单状态读取未清空输出的问题。此前游戏合并未初始化的栈数据，使 A 键快照混入 B 键及异常摇杆值；现在明确返回 32 字节调试手柄空状态、656 字节触摸屏空状态。实机已验证跳过开场影片、从标题进入存档槽选择、选槽及进入故事模式。外部截图为 `analysis/file-select-input-verified.png`。
- 已补齐游戏实际使用的 HDR 线性缩放拷贝。此前未实现的 1920×1080→960×540 拷贝让世界地图近乎全黑；补齐后已显示彩色场景。后端同时支持同类 R16Float 缩放，限定二维、基础 mip、单层及线性过滤，其他形态仍会报出未实现错误。
- 已在隔离测试目录验证重启后读回 1% 进度，进入第一关 Green Gardens，并完成左右移动、跳跃和越过第一个台阶。外部截图为 `analysis/first-level-native-verified.png`，逐帧渲染记录为 `analysis/level-frame6110.txt`。游戏混音器及 CoreAudio 日志记录到非零音频输出；影片 `audout` 的 PCM 播放仍未完成。
- `KIRBY_VERTEX_Y_FLIP=1` 和 `TOTK_GPU_WINDING_FLIP=1` 是目前的坐标方向实验开关。前者在最终编译的顶点 MSL 输出处转换 Y（包含电影的固定顶点程序），后者同步转换面朝向。世界地图和第一关已显示正确方向。此前标题及 UI 的局部错位还受派生顶点着色器遗漏 Y 转换影响，见下方 UI 修复；尚不能视为完整的 NVN 原点语义实现。
- 已修复坐标实验开关启用后的电影黑屏：电影顶点曾被排除在 Y 翻转之外，但仍应用了翻面后的剔除规则。逐帧记录确认电影四边形被剔除；临时关闭剔除恢复图像后，正式实现让电影顶点与面朝向共同转换，重新启动后已验证影片有画面且方向正确。证据为 `analysis/movie-depth-frame14249.log` 和 `analysis/movie-coordinate-final-verified.png`。
- 已定位标题重影的直接原因：NVN 设备默认深度区间为 `-w..w`，宿主全局状态却按 `0..w` 初始化，背景被 Metal 裁剪。宿主现在同步默认模式，着色器缓存的查询、变体哈希和索引也区分深度模式，避免复用未转换的旧顶点程序。标题、存档菜单和第一世界地图已回归。
- 已从世界地图第二个橙色入口进入第二关洞穴，并验证移动及跳跃；资源读取明确为 `map/Step/Level1/Stage2/Step01`。截图 `analysis/second-level-native-verified.png`，读取记录 `analysis/stage2-open-evidence.log`。用户报告的第二入口串到第一关在本次测试未复现，随后用户也确认第二关进入正常；尚不能据此认定该问题永久消失。
- 关卡仍有模糊和局部方向错误；暂停界面的未分配 `refractionDepthBuffer` 句柄已保留为无效描述符，并沿用后端的未绑定贴图处理；此前按暂停必退出现象已通过打开、关闭和恢复第一关的回归，截图为 `analysis/pause-native-verified.png`，这份旧证据中的菜单遮挡错位现已另行修复，见下方 UI 修复。完整关卡通关、后续世界、全流程存档与影片音频尚未通过验证，不能将此实验 App 当作已完成的移植。

## 预览操作

- `W/A/S/D`：左摇杆；世界地图向右走到橙色传送点后，`J` 进入关卡。
- `J`：手柄 A（菜单确认、关卡跳跃）；`K` / 空格：手柄 B；`I`：X；`U`：Y。
- 回车：`+`；Tab / Esc：`−`。按键按游戏当前的控制设置解释。
- `1`：显示 / 隐藏快捷键、FPS、着色器和系统负载提示。默认隐藏，首次按下即显示；按住不重复切换。
- `2`：补帧依次切换为关闭、30+30、刷新率一半、不限帧。使用最终游戏画面的 MetalFX 光流插值；当前采用平面深度和零相机运动作为输入，快速移动、遮挡变化及菜单文字可能重影。
- `3`：画质依次切换为 MetalFX 2K、原生 2K、关闭。MetalFX 从放大前的场景纹理生成 2560×1440；原生模式由游戏线程重建渲染目标。已验证第一关的 G-buffer、深度和主颜色均为 2560×1440；其他场景仍需逐一回归。
- 测试数据位于 `~/Library/Application Support/MacNativeGames/Kirby/tests/movie-path`，与预览 App 默认的 `Kirby/preview` 数据目录隔离。

## UI 坐标修复

- 问题是 UI 按钮背景、边框和文字分离，部分内容被翻到屏幕另一侧，并非这些贴图文件缺失。初次编译在 `shader_load` 中转换顶点 Y；缺失 varying / 分层绘制需要派生顶点函数时，`sh_src` 却读回未经转换的源文件。
- 两条编译路径现在共用幂等的 `kirby_shader_source`。保留源码及仅保留文件路径两种缓存模式均应用同一转换；片元阶段不改动。`tests/test_kirby_shader_source.py` 提取实际补丁中的代码编译验证，旧版本失败、修复后通过。
- 已实机复现并修复“返回 Select World”确认框的上下拆分按钮，证据 `analysis/world-selection-stable.jpg`（旧）和 `analysis/ui-fixed-world-return-dialog.jpg`（新）；暂停菜单和主菜单也已回归，截图 `analysis/ui-fixed-pause-menu.jpg`、`analysis/ui-fixed-main-menu.jpg`。证据均在外部宿主目录。

## 性能与 GPU 保活

- 2026-10-21 的战斗卡顿调查先用独立的 `Kirby/tests/perf` 存档复现，并在普通绘制路径采到频繁的 `getenv`。宿主适配现在先识别电影专用着色器，再读取电影放大的预览开关；电影颜色矩阵兼容路径也先核对绑定阶段和程序，再查询纹理与 uniform。打包启动器启用诊断环境值的一次性缓存，避免每次绑定程序重复查询未设置的日志开关。优化后同一首关敌人区域的 8 秒采样未再出现 `draw_inner → getenv`，仍有少量与录制、提交、上屏相关的环境读取。采样记录分别在外部 `analysis/kirby-battle-optimized-sample-20261021.txt` 和 `analysis/kirby-battle-final-sample-20261021.txt`；这只证明该热路径的重复查询被消除，不能代表所有战斗场景都稳定 60 帧。
- 原预览包较复杂场景曾测到帧时间 p50 约 19.64 ms、p95 约 21.26 ms，而优化包在首关敌人区域的 p95 仍约 17.1 ms；场景不同，不能据此计算提速比例。额外试验的 `TOTK_ARG_EPOCH` 与 `TOTK_TEX_SLOTS` 缓存通过了独立 GPU 探针和运行时一致性检查，但开启检查时未见明确帧时间收益，因此正式包未启用这两个开关。真正掉帧最严重的战斗场景仍需单独复测。
- 基础和 MetalFX 空间放大模式默认不运行额外自旋核；切到原生 2K 或任一补帧模式时自动恢复原有保活策略。`TOTK_GPU_KEEPALIVE=1` 保持原有常开策略，`=0` 完全关闭。其他游戏的默认策略未变。
- 第一关同场景对比中，基础模式保活开启时游戏 GPU p50 约 5.8 ms，另有每帧约 6.8 个、每个 1 ms 的自旋核；关闭后游戏 GPU p50 约 6–7 ms，整帧仍约 16.67 ms，取消了额外 GPU 工作。MetalFX 2K 关闭保活时也维持约 16.67 ms。原生 2K 和插值保留原有策略，避免据轻负载结果推断重负载表现。
- 对比记录 `analysis/perf-keepalive-ab.txt` 位于外部宿主目录；它反映此次第一关测试，未量测电功率，也不能视为全游戏 FPS 增幅。按需策略的目的是保留当前帧率并减少无用负载，为持续运行留出余量。最终包的自动启停已按基础 → 补帧 → 基础、MetalFX 2K → 原生 2K → 基础切换验证；`analysis/ui-perf-final-runtime.log` 记录启停与帧耗时，第一关基础及原生 2K 均测到约 16.67 ms。

## 打包语言和基础帧率

- 打包时按 `TOTK_LANG`、有效的 `LC_ALL` / `LC_MESSAGES` / `LANG`、macOS `AppleLanguages` 的顺序选择语言；`C` / `POSIX` 不是游戏语言。仅选择 RomFS 中确实存在的消息资源，随后回退到英语、日语。运行时可用 `TOTK_LANG` 覆盖打包选择。
- 当前基础版的 `msg/Eclair` 包含日语、美式 / 英式英语、欧洲 / 加拿大法语、德语、意大利语、欧洲 / 拉美西班牙语及荷兰语；未找到中文消息资源。简体中文打包环境因此选择 `en-US`，不会将文件名中的“中文”当作资源证据。
- 游戏内部帧节拍表位于基础版 main+`0x39a48c`，按 60 Hz 计拍；关卡原本使用第二项“两拍一帧”。启动补丁校验完整 `{1,2,3,4,5,6}` 原表后，仅把第二项改成一拍，解除基础 30 帧限制、以游戏 60 Hz 节拍运行；经过时间的更新计数由游戏原有逻辑处理。`2` 主动选择的 30+30 档仍保留。启动器同时默认 `DM_PRESENT_INTERVAL=display`，不再额外等待游戏请求的多刷新出图间隔。CPU / GPU 负载仍决定实际帧率，未对 60 Hz 以上的游戏模拟做适配。
- 实机采样 `analysis/kirby-frame-limit-sample.txt` 定位休眠路径 main+`0x55dc`，`analysis/frame-pacer-disassembly.txt` 记录调用路径；修正前第一关整帧约 33.33 ms / GPU 7 ms，修正后约 16.67 ms，截图 `analysis/frame-pacer-probe-move.jpg` 显示 60 FPS。相同 400 毫秒移动输入在 60 FPS 和 30+30 下均约 110 像素（1000 像素宽截图），未见倍速；这不是全流程速度验证。正式重编译并签名的 App 重新启动后，英语第一关再次显示 60 FPS，证据 `analysis/final-build-english-60fps.jpg`；`analysis/final-build-language-pacing.log` 保存最终运行节选。

## 快捷键适配与验证

- 提示开关与初始隐藏状态统一；启动器启用各提示组件，再由 `1` 统一控制可见性。
- 补帧直接接入最终游戏画面，不依赖 TOTK 的场景着色器、相机 uniform 和深度格式。实机曾记录 300 个游戏帧生成 299 张插值帧。
- MetalFX 2K 识别已登记的交换链、固定全屏顶点程序和 HDR 输入，保留原片元程序的颜色处理，避免只识别某一个片元变体而失效。
- 原生 2K 的指令修改在启动时逐条核对原值。纹理池 `GlbMemPool-Texture` 从 320 增至 576 MiB，`System` 父堆从 940 增至 1196 MiB，根分配器的五处初始化上限同步增加 256 MiB；宿主报告的应用内存池增加 512 MiB。只增加上层内存池会留下子堆耗尽的问题。
- 外部证据位于 `~/Downloads/Kirby_build/host/analysis/`：`shortcuts-texture-heap-fault.log` 记录纹理子堆耗尽，`shortcuts-root-memory.log` 记录旧根上限；`shortcuts-native-full-targets.log` 记录完整 2K 附件，`shortcuts-native-full-targets.jpg` 记录移动后的正确画面。
- `tests/test_kirby_shortcuts.py` 在项目外的临时目录应用实际补丁并编译验证提示开关、画质模式循环、分辨率发布及关闭后的恢复，无需个人游戏文件。
- 最终宿主的 `probe-gfx` 通过 108 个出图节拍用例，记录为外部 `analysis/shortcuts-gfx-probe.log`。这验证模式的节拍策略。四个模式另在第一关用相同的 400 毫秒右移输入对比，1000 像素宽截图中的移动距离约为 110–120 像素，未见明显变速；证据为外部 `analysis/shortcuts-speed-*.jpg`。这次对比受 GPU 负载限制，不能据此保证其他刷新率和轻负载场景的模拟速度。

## 源码组织

- `native-preview.patch` 是应用于固定宿主源码提交 `f5cc1519c5c6aed8b21c20317a9cee15f3f6d746` 的 `games/totk` **项目外副本**的实验适配。后续宿主已改变多个相同文件，不能对当前 `HEAD` 直接套用此补丁。它包含旧版 SDK 启动 ABI、部分 IPC、VI、HID、音频、FFmpeg 影片解码及分段显存池适配；移除了 TOTK 专属游戏补丁，改用带原指令保护的卡比分辨率与内存预算适配。实验逻辑尚未达到发布质量。打包脚本会将构建所用的 Homebrew 动态库和许可文件收进预览 App。
- `patch_sdk.py` 仅针对已验证的基础版 SDK 重写镜像，替换五个会因缺少 Switch HID 共享内存而中断的读取入口。它返回空状态，用于启动探针，不是完整输入实现。
- 通用容器提取和带 build ID 保护的模块重写改动保留在原有提取器与 D2R 重写器中。

## 开发构建与打包

需要 Apple silicon Mac、macOS 26 或更高、Xcode 命令行 / Metal 工具、Python 3.14，以及 Homebrew 的 `opus`、`libvpx`、`ffmpeg`。Python 依赖见 [`games/totk/requirements.txt`](../totk/requirements.txt)。游戏基础版、密钥和六份已验证的共享字体由使用者自行提供。

先在项目外建立宿主源码副本。以下命令仅准备源码，`/path/outside-repository` 须替换为真实的项目外路径；此处不解包游戏、不生成验证报告：

```sh
kirby_repo="$(git rev-parse --show-toplevel)"
kirby_work="/path/outside-repository/Kirby_build"
kirby_host="$kirby_work/host"
mkdir -p "$kirby_host"
git archive f5cc1519c5c6aed8b21c20317a9cee15f3f6d746 games/totk | tar -x -C "$kirby_host" --strip-components=2
git -C "$kirby_host" apply --check -p1 "$kirby_repo/games/kirby/native-preview.patch"
git -C "$kirby_host" apply -p1 "$kirby_repo/games/kirby/native-preview.patch"
```

宿主还须有下列来自自己游戏数据的已验证输入。这一阶段仍是开发者工作流，不应将已有探针报告复制到不同版本上：

| 宿主相对路径 | 内容 |
|---|---|
| `extracted/v0/exefs`、`extracted/v0/elf` | 完整性验证后的基础版代码、各模块 ELF inventory |
| `rewritten/v0` | 三个模块的 `.patched.bin` 和 `.fixups.tsv` |
| `extracted/v0/romfs` | 验证后的 `romfs.bin`、`runtime-index.bin`、`index.json` |
| `extracted/firmware/shared-fonts` | 六份 BFTTF 文件和通过校验的 `manifest.json` |
| `analysis/phase12-validation.json` | 模块验证及探针产生的 `status: probe`、`rom_version: v0` 与各重写模块 SHA-256 |
| `build/shader-service`、`build/spirv-cross` | 原生着色器翻译服务与 SPIRV-Cross 工具 |

通用 ExeFS 提取器新增 `--title-id 01007E3006DDA000`；RomFS 提取器继续使用该 manifest 中的 title ID。默认值及旧 manifest 的回退仍为 TOTK。重写器的 SDK 跳转表按卡比模块 build ID 和原始指令核对，`patch_sdk.py` 另对已知 SDK 重写镜像做 SHA-256 保护，原地修改时仅接受未打过该补丁的镜像。SDK 补丁后的哈希也必须进入最终验证报告。

完成这些准备后，创建外部虚拟环境，再生成运行时表、编译和打包：

```sh
python3.14 -m venv "$kirby_work/.venv"
"$kirby_work/.venv/bin/python" -m pip install -r "$kirby_host/requirements.txt"
"$kirby_work/.venv/bin/python" "$kirby_host/scripts/prepare_runtime.py"
make -C "$kirby_host" PY="$kirby_work/.venv/bin/python" build/totk-native
"$kirby_work/.venv/bin/python" "$kirby_repo/games/kirby/package_preview.py" \
  --host "$kirby_host" --output "$kirby_work/apps/Kirby Native Preview.app"
codesign --verify --deep --strict "$kirby_work/apps/Kirby Native Preview.app"
```

打包器要求输出为不存在的新 `.app` 路径，并将 Homebrew 动态库及许可文件收入 App；它不会下载游戏文件或创建探针报告。替换已有 App 前先退出游戏；保留用户数据目录即可复用进度和缓存。

## 自动测试与验证边界

在源码根目录运行，虚拟环境及原生测试可执行文件均放在项目外：

```sh
python3.14 -m venv /path/outside-repository/kirby-tests-venv
/path/outside-repository/kirby-tests-venv/bin/python -m pip install -r games/totk/requirements.txt
PYTHONDONTWRITEBYTECODE=1 /path/outside-repository/kirby-tests-venv/bin/python \
  -m unittest discover -s tests -v
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
  tests/test_romfs_paths.c -o /path/outside-repository/test-romfs-paths
/path/outside-repository/test-romfs-paths
```

2026-10-21 本地全套 47 项通过；其中卡比的 8 项测试验证打包语言回退、基础节拍表保护、快捷键状态、派生着色器转换和保活策略。它们从实际适配补丁提取代码编译运行，或读取生成的小型资源索引，不需要游戏、密钥、存档或 GPU 渲染；原生代码测试需要 macOS / clang。

外部宿主另运行过 `TOTK_HEADLESS=1 KIRBY_PREVIEW=1 build/totk-native /path/to/rewritten/v0 probe-gfx`，含 108 个出图节拍用例。它验证宿主策略，不替代游戏实测。菜单、关卡、UI、60 帧和画质切换的实机证据见前文；GitHub 源码 CI 不执行个人游戏文件的完整构建或全流程游玩。

## 数据与证据位置

- 正常预览的数据根目录为 `~/Library/Application Support/MacNativeGames/Kirby/preview`，包含 `profile`、`proof`、`slot`、`shader-cache` 和追加写入的 `latest.log`。
- 本地隔离测试使用同一 Kirby 用户数据目录下的 `tests/movie-path`；测试存档不得覆盖正常预览存档。
- 本次开发宿主、构建和证据位于项目外的 `~/Downloads/Kirby_build`，文中的 `analysis/...` 相对此处的 `host`。这些本地截图和日志不随 Git 仓库发布。
- 本机长期产物约定放在 `/Volumes/mac-APFS/MacNativeGames-artifacts`：App 使用 `apps`，开发缓存使用 `development`。卷可用时使用该外部位置；源码内不保存 App、解包数据或缓存，也不放指回这些目录的链接。

实验宿主、解包内容、编译结果和日志必须存放在项目目录外。现有本机证据位于 `~/Downloads/Kirby_build` 和 `~/Library/Application Support/MacNativeGames/Kirby/tests`。实验补丁可在 `games/totk` 的外部副本根目录执行 `git apply --check -p1 /绝对路径/games/kirby/native-preview.patch` 进行上下文检查；不要直接应用到 TOTK 正式源码。

# 星之卡比 新星同盟（基础版）原生移植实验

目标 NSP 的 title ID 为 `01007E3006DDA000`，内部版本为 0。文件名中的 `4.1.0` 不是 NSP 内的更新版本。移植沿用项目的 ARM64 游戏代码直跑、Horizon 服务接管和 Metal NVN 后端；当前仍是开发预览，不能作为可玩的 App 发布。

## 已验证的进度

- ExeFS 和 RomFS 完整性验证通过；RomFS 共 4,442 个文件、3,080,511,292 字节。
- 三个游戏模块经重写后通过原生 PLT 探针，游戏进入 `nnMain`、初始化音频和 Metal，并向原生窗口持续提交帧。
- 实验宿主已接管开场 MP4 的 H.264 视频及 AAC 解码，能从 `avcc`/`esds` 参数解析配置、解出帧并交还给游戏。`audout` 缓冲区事件和释放队列已有最小实现，避免此前的崩溃；它尚未播放 PCM，因此音频仍是静音。
- 开场影片已在原生窗口显示运动画面。黑屏的直接原因是电影 YUV 转 RGB 的 64 字节矩阵为零；兼容补丁在最终 GPU uniform 绑定处提供有限范围 BT.709 矩阵，同时核对电影顶点程序及两张 NV12 纹理。原影片的色彩空间由 `ffprobe` 确认，实机截图位于外部宿主的 `analysis/movie-gpu-matrix-verified.png`。矩阵为何未由游戏初始化仍需继续追查。
- 已修复旧版 SDK 调试手柄和触摸屏单状态读取未清空输出的问题。此前游戏合并未初始化的栈数据，使 A 键快照混入 B 键及异常摇杆值；现在明确返回 32 字节调试手柄空状态、656 字节触摸屏空状态。实机已验证跳过开场影片、从标题进入存档槽选择、选槽及进入故事模式。外部截图为 `analysis/file-select-input-verified.png`。
- 已补齐游戏实际使用的 HDR 线性缩放拷贝。此前未实现的 1920×1080→960×540 拷贝让世界地图近乎全黑；补齐后已显示彩色场景。后端同时支持同类 R16Float 缩放，限定二维、基础 mip、单层及线性过滤，其他形态仍会报出未实现错误。
- 已在隔离测试目录验证重启后读回 1% 进度，进入第一关 Green Gardens，并完成左右移动、跳跃和越过第一个台阶。外部截图为 `analysis/first-level-native-verified.png`，逐帧渲染记录为 `analysis/level-frame6110.txt`。游戏混音器及 CoreAudio 日志记录到非零音频输出；影片 `audout` 的 PCM 播放仍未完成。
- `KIRBY_VERTEX_Y_FLIP=1` 和 `TOTK_GPU_WINDING_FLIP=1` 是目前的坐标方向实验开关。前者在最终编译的顶点 MSL 输出处转换 Y（包含电影的固定顶点程序），后者同步转换面朝向。世界地图和第一关已显示正确方向，但标题及选世界页的部分 3D/贴图仍存在方向错误，不能视为完整的 NVN 原点语义实现。
- 已修复坐标实验开关启用后的电影黑屏：电影顶点曾被排除在 Y 翻转之外，但仍应用了翻面后的剔除规则。逐帧记录确认电影四边形被剔除；临时关闭剔除恢复图像后，正式实现让电影顶点与面朝向共同转换，重新启动后已验证影片有画面且方向正确。证据为 `analysis/movie-depth-frame14249.log` 和 `analysis/movie-coordinate-final-verified.png`。
- 已定位标题重影的直接原因：NVN 设备默认深度区间为 `-w..w`，宿主全局状态却按 `0..w` 初始化，背景被 Metal 裁剪。宿主现在同步默认模式，着色器缓存的查询、变体哈希和索引也区分深度模式，避免复用未转换的旧顶点程序。标题、存档菜单和第一世界地图已回归。
- 已从世界地图第二个橙色入口进入第二关洞穴，并验证移动及跳跃；资源读取明确为 `map/Step/Level1/Stage2/Step01`。截图 `analysis/second-level-native-verified.png`，读取记录 `analysis/stage2-open-evidence.log`。用户报告的第二入口串到第一关在本次测试未复现，随后用户也确认第二关进入正常；尚不能据此认定该问题永久消失。
- 关卡仍有模糊和局部方向错误；暂停界面的未分配 `refractionDepthBuffer` 句柄已保留为无效描述符，并沿用后端的未绑定贴图处理；此前按暂停必退出现象已通过打开、关闭和恢复第一关的回归，截图为 `analysis/pause-native-verified.png`，但菜单仍有遮挡错位。完整关卡通关、后续世界、全流程存档与影片音频尚未通过验证，不能将此实验 App 当作已完成的移植。

## 预览操作

- `W/A/S/D`：左摇杆；世界地图向右走到橙色传送点后，`J` 进入关卡。
- `J`：手柄 A（菜单确认、关卡跳跃）；`K` / 空格：手柄 B；`I`：X；`U`：Y。
- 回车：`+`；Tab / Esc：`−`。按键按游戏当前的控制设置解释。
- `1`：显示 / 隐藏快捷键、FPS、着色器和系统负载提示。默认隐藏，首次按下即显示；按住不重复切换。
- `2`：补帧依次切换为关闭、30+30、刷新率一半、不限帧。使用最终游戏画面的 MetalFX 光流插值；当前采用平面深度和零相机运动作为输入，快速移动、遮挡变化及菜单文字可能重影。
- `3`：画质依次切换为 MetalFX 2K、原生 2K、关闭。MetalFX 从放大前的场景纹理生成 2560×1440；原生模式由游戏线程重建渲染目标。已验证第一关的 G-buffer、深度和主颜色均为 2560×1440；其他场景仍需逐一回归。
- 测试数据位于 `~/Library/Application Support/MacNativeGames/Kirby/tests/movie-path`，与预览 App 默认的 `Kirby/preview` 数据目录隔离。

## 快捷键适配与验证

- 提示开关与初始隐藏状态统一；启动器启用各提示组件，再由 `1` 统一控制可见性。
- 补帧直接接入最终游戏画面，不依赖 TOTK 的场景着色器、相机 uniform 和深度格式。实机曾记录 300 个游戏帧生成 299 张插值帧。
- MetalFX 2K 识别已登记的交换链、固定全屏顶点程序和 HDR 输入，保留原片元程序的颜色处理，避免只识别某一个片元变体而失效。
- 原生 2K 的指令修改在启动时逐条核对原值。纹理池 `GlbMemPool-Texture` 从 320 增至 576 MiB，`System` 父堆从 940 增至 1196 MiB，根分配器的五处初始化上限同步增加 256 MiB；宿主报告的应用内存池增加 512 MiB。只增加上层内存池会留下子堆耗尽的问题。
- 外部证据位于 `~/Downloads/Kirby_build/host/analysis/`：`shortcuts-texture-heap-fault.log` 记录纹理子堆耗尽，`shortcuts-root-memory.log` 记录旧根上限；`shortcuts-native-full-targets.log` 记录完整 2K 附件，`shortcuts-native-full-targets.jpg` 记录移动后的正确画面。
- `tests/test_kirby_shortcuts.py` 在项目外的临时目录应用实际补丁并编译验证提示开关、画质模式循环、分辨率发布及关闭后的恢复，无需个人游戏文件。
- 最终宿主的 `probe-gfx` 通过 108 个出图节拍用例，记录为外部 `analysis/shortcuts-gfx-probe.log`。这验证模式的节拍策略。四个模式另在第一关用相同的 400 毫秒右移输入对比，1000 像素宽截图中的移动距离约为 110–120 像素，未见明显变速；证据为外部 `analysis/shortcuts-speed-*.jpg`。这次对比受 GPU 负载限制，不能据此保证其他刷新率和轻负载场景的模拟速度。

## 源码组织

- `native-preview.patch` 是应用于 `games/totk` **副本**的实验宿主适配。它包含旧版 SDK 启动 ABI、部分 IPC、VI、HID、音频、FFmpeg 影片解码及分段显存池适配；移除了 TOTK 专属游戏补丁，改用带原指令保护的卡比分辨率与内存预算适配。实验逻辑尚未达到发布质量。打包脚本会将构建所用的 Homebrew 动态库和许可文件收进预览 App。
- `patch_sdk.py` 仅针对已验证的基础版 SDK 重写镜像，替换五个会因缺少 Switch HID 共享内存而中断的读取入口。它返回空状态，用于启动探针，不是完整输入实现。
- 通用容器提取和带 build ID 保护的模块重写改动保留在原有提取器与 D2R 重写器中。

实验宿主、解包内容、编译结果和日志必须存放在项目目录外。现有本机证据位于 `~/Downloads/Kirby_build` 和 `~/Library/Application Support/MacNativeGames/Kirby/tests`。实验补丁可在 `games/totk` 的外部副本根目录执行 `git apply --check -p1 /绝对路径/games/kirby/native-preview.patch` 进行上下文检查；不要直接应用到 TOTK 正式源码。

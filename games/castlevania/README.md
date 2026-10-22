# 恶魔城：贝尔蒙特的诅咒 本机移植记录

状态（2026-10-21）：**主游戏 1.1.0 已在原生 Mac 测试 App 中完成首次设置、序章影片播放、进入关卡、方向移动和首次存档写入；完整流程尚未逐关卡验收**。运行时直接执行改写后的 ARM64 游戏模块，Metal 绘制游戏画面，CoreAudio 输出游戏 PCM。首次语言页的确认动作要求长按 A；随后选择确认按键和亮度，游戏写入 `HasLaunchedBefore=1` 并进入标题。选择“新游戏”后的序章 H.264 影片由 macOS VideoToolbox 解码至结尾，随后出现角色对话和关卡 HUD。隔离测试档写出 `BuildSave_0`，重新启动后标题出现“继续游戏”，选择后能播放后续影片并进入对话、关卡 HUD；是否真正恢复到存档位置仍待验证。用户现要求先解决主游戏关卡中的渲染与帧时间波动，画廊不再处理。两份 DLC 数据已随 App 保存并向游戏枚举，游戏在偏好文件中记录了 `dlc-1`、`dlc-2` 和对应解锁标记；关卡内使用和资源挂载尚未验证。

## 输入与已验证结果

共享目录位于 `~/Downloads/共享/[恶魔城：贝尔蒙特的诅咒][Castlevania Belmont's Curse]`。组合 XCI 包含两个基础 title：主游戏 `0100BA4026E94000` 和独立的数字音乐与美术画廊 `01005F4027E94000`。项目的 ExeFS/RomFS 提取器现在可以按 `--title-id` 选择组合 XCI 中的一个 title，更新合并器也可传入该 ID；默认的王国之泪单 title 构建行为不变。

| 内容 | 本机结果 |
|---|---|
| 主游戏基础版（组合 XCI） | ExeFS 各文件哈希通过，RomFS 六级有效哈希及目录索引通过：3,075 个文件、2,987,550,132 字节，SHA-256 `04591cb93e89e024603dffdf0713762fa2af1bfb68ae660690f6572aa6248653`。 |
| 主游戏 1.1.0 更新 NSP | ExeFS 校验通过；与组合 XCI 中主游戏的基础 Program NCA 经 BKTR 合并，六级校验通过：3,101 个文件、3,600,101,664 字节，SHA-256 `2ba74cc0e68efc9202880b6ea92d2e9cc5193069a7bbc17e85d1ffb68fa77247`。此资源已进入原生 App，启动至游戏自身语言菜单。 |
| 标称“本体 v1.1.0”的独立 NSP | Program NCA 声明的区段超出其 558,891,008 字节的 NCA 边界；不能替代组合 XCI 中的主游戏本体。 |
| 画廊基础版（组合 XCI） | ExeFS 校验通过；RomFS 的已引用哈希块与零填充未用区域经检查，但目录表起点约 1.98 GB，超过约 1.33 GB 的 RomFS 大小，无法索引。用户现要求不处理画廊。 |
| 画廊 1.1.0 更新 NSP | ExeFS 校验通过；按用户当前要求不合并或打包。 |
| 两份 DLC NSP | 各含元数据 NCA 和约 101 KB 的 PublicData NCA。两份 PublicData 的 RomFS 均通过六级 IVFC 校验，各有一个 `VENOM` 文件，镜像同为 924 字节、SHA-256 `853d89ef4aad9f627401c79d2cb12c6533dced4247f3f2202f94f4c6a7a2ba05`；原始 NSP 仍须保留各自 title/元数据。App 按各 title 保存原始 RomFS 和已验证的 `VENOM` 文件；宿主向 `nn::aoc` 枚举两份内容，并实现只读 `MountAddOnContent`。游戏实际写入 `dlc-1`、`dlc-2`、`bc_1`、`bc_2` 为 1；尚未观察到挂载调用或关卡内效果。 |
| 帧率改善 Mod RAR | 含替换的 `exefs/main`，说明为启用三缓冲。它是可选 Mod，不是官方内容；尚未验证与原生改写器、1.1.0 运行时兼容，不纳入当前主游戏基线。 |

主游戏 1.1.0 的 `main`、`sdk`、`subsdk0` 均已生成 ARM64 改写镜像。全量扫描主模块文本发现 18 处 `br x18`：16 处为有界跳转表，两处（`0x375a7ec`、`0x3daf81c`）从对象字段读函数指针，属于间接尾跳转。两处跳转前均从栈恢复 x16/x17 等寄存器，不能把它们当作可丢弃的暂存寄存器。改写器针对构建号 `0f1169aa7d0fa4529c861f96adec306e` 核对目标选择器及跳转代码哈希，只允许各自八个已登记的目标；落地垫在进入目标前恢复 x16/x17，未知目标明确中止。该构建另有九处通过 x18 动态调整 SP，已核对旧 SP 保存在 x8/x10 的代码并用旧 SP 恢复暂存寄存器。两类特殊站点用 Unicorn 与原指令完成 84 组寄存器、栈、内存和条件标志等价试验；其后完成主模块结构核验并实际启动游戏。局部语义试验和菜单启动仍不等于整款游戏已通过游玩验收。

游戏资源显示 Unity/IL2CPP 内容及 `Plugins/cimgui.nro`；主模块确实导入 `nn::ro` 的模块注册、加载与符号查找接口。现有宿主已适配本游戏启动所需的服务、RomFS、音频与 Metal 图形路径，实际进入游戏菜单；尚待逐关卡验证是否调用动态 NRO 路径。

菜单画面原本在 Mac 窗口比原始游戏帧暗：游戏交换链格式 `0x38` 为 sRGB，宿主采样时解码为线性值，却向非 sRGB 的 `CAMetalLayer` 写出。Castlevania 专用前端改用 `MTLPixelFormatBGRA8Unorm_sRGB`，重启后以实际窗口画面确认菜单文字和金色边框可读。原始帧与窗口截图保存在外部 `native-host/menu-raw-current.png`、`native-host/menu-window-current.png`。

首次设置流程已验证：`ui-firstlaunch` Unity 资源把确认动作绑定为 `InputActionsToUnityEvent.InputMode.LongPress`，其 UnityEvent 调用 `SplashScreenSettingsBase.CloseSetting`（主模块 `0x1f19300`）。按住 A 六秒的一次性指令陷阱实际命中该函数，见外部日志 `castlevania-20261021-160038-61282.log`；去掉陷阱重跑后到达确认按键页，选择 A，进入亮度页并调到测试档的 0.6，再长按 A 到达标题菜单，隔离档写入 `HasLaunchedBefore=1`。先前改变文字语言在 SDK 镜像偏移 `0x3f76c0` 处崩溃，定位为 `nn::oe::EnterExitRequestHandlingSection` 解引用未初始化的 Switch 系统对象；本机宿主接管进入/离开退出请求处理区间后，已实际切换至繁体中文再恢复简体中文，未再崩溃。接入 DLC 后另触发 `nn::fs::GetFreeSpaceSize("save")`；宿主现在接受裸挂载名，并从本机存储查询容量。

选择“新游戏”后 `HUDSetImagesParameters.SetImagesParameters` 在主模块 `0x1f73a9c` 检查到空的 `Image` 引用，抛出 `NullReferenceException`。IL2CPP 元数据表、指令陷阱和 `ui-hud` Unity 资源共同确认该位置；资源中的 `HUD_Health_Display` 及 `HUD_Mana_Display` 的七项 `_images` 列表第 2 项就是空引用。先前把相邻的异常入口误判为数组越界已纠正。本作专用运行时补丁在核对原指令后只跳过空的单项处理，`Start` 仍逐项处理列表其余元素；测试 App 在不设置诊断变量的情况下越过该异常并到达影片解码阶段，外部日志 `castlevania-20261021-160513-62021.log`。新版主游戏 App 已纳入此修复。宿主还已适配 SDK 的 `clock_gettime(0)`（`std::chrono::system_clock::now()` 使用）。随后场景创建 `movie::Decoder`，原库调用 `NvMMLiteOpenVideo` 打开 Switch 硬件解码器并中止；在 `subsdk0+0x68010` 的陷阱读到编解码器编号 `0x105`，外部日志 `castlevania-20261021-155619-60590.log`。从游戏 `narration-videos-720p` Unity 资源取出的序章 `.m4v` 经 `ffprobe` 确认为 H.264 画面加两路 AAC 音轨。测试宿主为本作的 H.264 缓冲模式接入 VideoToolbox，音轨仍由原 SDK 的软件 AAC 路径处理。外部日志 `castlevania-20261021-161734-64230.log` 记录 4,609 个 H.264 帧解码至影片结束且没有解码报错；窗口截图 `native-host/prologue-h264-vt-window.png` 确认真实显示了影片画面。结束回调 `FmodVideoPlayerSound.VideoEnded` 原先在 `main+0x1d2a784` 抛出空引用；诊断陷阱日志 `castlevania-20261021-162704-65896.log` 证实回调参数有效，空的是 `mVideoPlayer`，而 `StopSound` 会清空该字段。本作专用补丁使迟到的回调经原函数收尾路径返回；正常节奏测试已在 `castlevania-20261021-164236-68643.log` 到达对话与关卡，写入隔离测试档的 `BuildSave_0`。`TOTK_MOVIE_PACE=0` 加速诊断会使游戏占满八个输出缓冲并停在黑场，不作为实际播放验收模式。此前关卡实际画面未正常合成：外部 `native-host/texdump-scene-115000.png` 有完整场景绘制，后处理纹理 `texdump-scene-115100.png` 却是品红色，最终也呈品红色；逐绘制记录在同一日志的 F31297。此轮还发现重复录制同一 Unity 命令缓冲区会耗尽宿主的 16 KiB 控制内存记号，导致录制副本与内存持续增长；本作专用重置使标记重新写入，回收扫描延后释放当前提交正在使用的副本。`castlevania-20261021-170619-72883.log` 的续读测试运行约九分钟、录制 438 万次后活跃副本仍保持有界，进程内存约 1.7–2 GB，未再次触发 24 GB 看门狗；`probe-gfx` 自检通过，见外部 `native-host/current-submit-probe-gfx.log`。游戏调用 `WindowCrop 0,0 1280x720`，实际窗口已正确裁切和放大；原始交换链截图右侧、下方的品红区域不在用户窗口中，后续已定位为场景纹理没有接入首个后处理通道。


后处理逐绘制记录显示，游戏把场景画进纹理序号 N，但首个全屏通道绑定相邻的 N+1，宿主读到的仍是清屏品红色。本作专用适配仅在对应片段着色器、同帧、同尺寸的首个后处理通道，把采样源接到刚绘制的场景纹理。标题窗口截图 `native-host/scene-feed-refined-title.png` 呈现城堡与月亮；较宽的诊断版本在续读后的关卡显示巴黎城和角色，截图 `native-host/scene-feed-gameplay-still.png`。保持右方向两秒后角色与镜头均移动，截图 `native-host/scene-feed-move-right.png`。收窄版本也在正常节奏影片结束后进入关卡，显示角色、背景和 HUD，见 `native-host/scene-feed-refined-gameplay-hud.png`；其 A/B 负控制是 `CASTLEVANIA_SCENE_FEED=0`。

关卡渲染不稳定的另一个根因是阶段掩码被宿主当作“绑定整个程序”。`castlevania-20261021-193812-95644.log` 的绑定记录显示，游戏先用掩码 `0x3` 绑定顶点与片元程序，再用空程序和掩码 `0x3c` 清除无关阶段；旧宿主却把正在使用的图形程序一并清掉。旧关卡回放每 300 帧丢弃约 16–18 万次绘制（`castlevania-20261021-193029-94480.log`）。本作专用适配在空程序绑定的掩码不含顶点或片元位时保留图形程序，`CASTLEVANIA_MASKED_BIND=0` 可作负控制；修复后的 `castlevania-20261021-194242-96344.log` 进入关卡、角色移动后不再报告无程序绘制，`native-host/masked-world2-window.png` 留有窗口画面。该运行在没有逐帧截图的关卡窗口中，帧间隔的 300 帧分组通常为 `>16.7 ms` 零帧、p99 约 10 ms；诊断命令连续截图造成的短时停顿不计入游戏性能结论。

旧包在首次看到新场景时仍会同步翻译或编译着色器和 Metal 管线，用户运行日志 `castlevania-20261021-192118-93049.log` 有 160–177 ms 长帧，GPU 仅约 1–3 ms。本作的 `prepare_shader_seed.py` 从已验证主游戏的本机运行时缓存生成外部着色器预热包，`build_app.py --shader-seed <外部目录>` 把它连同哈希清单收入 App；首次启动只向用户数据目录导入缺失的缓存文件。`castlevania-20261021-195038-97714.log` 在全新隔离缓存中导入 258 个着色器的 775 个文件，并在约 198 ms 内预热 182 条渲染管线，随后进入可操作关卡并向右穿过街区，窗口截图在外部 `native-host/seed-playable-window.png`、`seed-playable-move-window.png` 和 `seed-street-extended-window.png`。以关卡段第 23,000 帧起统计，旧用户日志 12 个 300 帧区间中有 9 个现场编译长帧（单次编译最长 133.1 ms），新的隔离运行有 51 个区间，其中 46 个没有超过 16.7 ms 的帧，p99 中位数 9.91 ms；新运行没有现场编译长帧或无程序丢弃。预热覆盖已游玩场景，未探索的新关卡仍可能首次生成新的变体。

## 游玩闪退与快捷键（2026-10-21）

用户游玩日志 `castlevania-20261021-201728-2871.log` 在约第 15,000 帧由游戏 SDK `Break` 退出。客体调用链的 `main+0x1bb3ff0` 对应 `PlatformLocomotion.CanGoTo`，其后调用的 `main+0x1bd6840` 对应 `Platform.IsConnectedTo`；反汇编显示连接字段为空会落到 `main+0x1bd68a4` 的 IL2CPP 空引用异常。恶魔城专用补丁核对该指令原值后，让无连接的平台判定返回 false，并恢复原函数保存的寄存器和栈。独立 `probe-platform-null` 直接调用空连接分支，验证返回 false。隔离存档运行日志 `castlevania-20261021-224027-22882.log` 已从“继续游戏”经过影片、对话运行至 5 万帧以上，未再出现同一 `Break`；这覆盖了该异常路径，但不代表其他关卡已全面验收。

恶魔城专用快捷键：`1` 显示或隐藏性能信息和快捷键说明；`2` 在游戏默认帧节奏、屏幕刷新率、30 FPS 之间循环；`3` 在标准放大与 MetalFX 空间放大之间切换。2、3 的当前档位会在窗口中央短暂提示，1 打开信息时说明持续显示。以前沿用的王国之泪补帧与 2K 页面切换不适用于恶魔城，已改为以上实际可用的输出控制。隔离测试的 30 FPS 档连续 300 帧中位帧间隔为 33.33 ms；MetalFX 档建立了从 1920×1080 到 3456×1944 的输出放大器；1 键关闭后窗口截图底部的性能信息像素数从 16,950 变为 0。测试截图与运行日志均在项目目录外的 `~/Downloads/Castlevania_build/native-host/`、用户日志目录中。

## 外部工作位置与后续验收

本轮解包、合并日志、改写镜像、着色器缓存、测试截图、App 均在项目外的 `~/Downloads/Castlevania_build`。新增的 DLC 提取入口为 `extract_romfs.py --keys <密钥路径> --source <DLC NSP> --title-id <DLC title ID> --output <外部目录>`，直接核对 PublicData RomFS 哈希链并在输出目录写入 `source-manifest.json`、`index.json` 和 `romfs.bin`。本机两份 DLC 的命令行复验产物位于外部 `main/addons-verified/<title ID>/`。主模块改写位于外部 `main/update/rewritten-indirect/`，用 `games/castlevania/verify_rewrite.py --nso <主模块 NSO> --rewrite <改写目录>` 复验特殊站点。外部 `native-host/boot-gpu.log` 与截图记录游戏真实绘制和菜单，`build-main-app-native-20261021.log` 记录此前主游戏 App 打包；原正式预览包保留在 `development/恶魔城：贝尔蒙特的诅咒-旧正式预览-20261021.app`。此前 App 的 `--check`、深度签名校验和 `probe-gfx` 通过；容器与更新的 26 项合成测试在外部 Python 3.14 虚拟环境通过，日志为 `test-containers-py314-20261021.log` 和 `test-updates-py314-20261021.log`。不设置图形诊断变量的原生启动在 `castlevania-20261021-173853-78326.log` 显示两份附加内容可枚举及正常标题背景，窗口截图为 `native-host/formal-app-title-default.png`。此前正式路径运行的 `castlevania-20261021-174443-79586.log` 记录影片 5,551 帧播放完成、零丢帧，随后进入有 HUD 的关卡；`native-host/formal-app-gameplay-settled.png` 为实际窗口画面，`formal-app-move-right.png` 记录按右方向后的角色与镜头位置。当前运行时以 `games/castlevania/build_app.py --work <外部工作目录> --shader-seed <外部预热包> --out <外部 App 路径>` 重打包，日志为 `native-host/build-masked-seeded-app.log`；新包已放在外部正式路径 `apps/恶魔城：贝尔蒙特的诅咒.app`，上一正式包保留在 `development/恶魔城：贝尔蒙特的诅咒-渲染性能前-20261021.app`。新包从正式路径启动的 `castlevania-20261021-200012-225.log` 再次导入并预热 258 个着色器，标题截图在外部 `native-host/formal-seeded-title-window.png`，签名、`--check` 与 `probe-gfx` 通过。约定的 `/Volumes/mac-APFS/MacNativeGames-artifacts` 卷未挂载；源码目录内没有游戏数据或 App。原始游戏文件和密钥未改动。

其后已将闪退修复与恶魔城专用 1/2/3 快捷键打入同一正式路径 `apps/恶魔城：贝尔蒙特的诅咒.app`，上一版归档在外部 `development/恶魔城：贝尔蒙特的诅咒-闪退修复前-20261021.app`。正式路径的 `castlevania-20261021-225216-25672.log` 记录三键输入、120 Hz 节奏与 MetalFX 放大，窗口截图 `native-host/formal-crash-shortcuts-title.png`；系统截图 `native-host/formal-shortcut-toast-screen.png` 记录中央档位提示。新版 `--check`、深度签名校验、`probe-platform-null`、`probe-gfx` 均通过，隔离测试结束后进程已正常关闭。

帧率显示补修（同日）：前一版启动器把 `TOTK_FPS_OVERLAY` 默认设为 `0`，使 1 键只能显示其余性能信息。去掉该默认值后，在不设置此变量的正式 App 中按 1 键，右上角实测显示 `FPS 120 3456x1944`；再次按 1 键，右上角绿色像素由 4244 变为 0。验证图 `native-host/fps-overlay-formal-path-on.png` 和 `native-host/fps-overlay-no-override-after-fix-off.png` 位于外部 `Castlevania_build`。原正式 App 已归档到外部 `development/恶魔城：贝尔蒙特的诅咒-FPS修复前-20261021.app`，更新版保留原正式路径；`--check` 与深度签名校验通过。

下一阶段须从新版主游戏 App 进一步验证后续关卡，并在游戏中观察两份 DLC 的挂载与效果。画廊按用户当前要求不处理。

## 死亡与刷怪问题调查（2026-10-22）

玩家日志 `castlevania-20261021-230415-28569.log` 在死亡时进入 `DrawFullscreenQuadAnchorToEntity.OnUpdate` 的空引用异常。恶魔城专用补丁让已失去锚定实体的全屏淡出绘制跳过该次更新；隔离运行不再出现原地址，但随后进入 `Pathfinding.ThreadControlQueue.Pop` 的托管异常。寻路线程的无异常退出补丁尚未通过死亡复验，已改为仅在 `TOTK_PATH_QUEUE_EXPERIMENTAL=1` 时启用。测试版 4 和外部日志 `castlevania-20261021-234823-40129.log`、`castlevania-20261021-235108-40543.log`、`castlevania-20261021-235304-40852.log` 均不能作为死亡问题已修复的证据；正式 App 尚未替换。较新的测试存档还出现关卡状态载入空引用或停滞，需独立排查。玩家原存档未改动。

怪物出现时原日志有 539 ms 长帧，其中约 527 ms 在提交与出图，同帧首次创建 6 个着色器库和 4 条管线。外部 `main/shader-seed-extended-20261021` 汇总实玩缓存中的 335 个着色器和 599 条管线记录；测试版 3 的隔离运行日志 `castlevania-20261021-233645-37213.log` 在已走过的关卡段没有运行中编译着色器或管线的长帧。然而同一日志仍有最高 452 ms 的非编译长帧，GPU 与提交耗时均很低，因此刷怪帧时间问题尚未全部解决。所有预热包、测试 App、存档副本及截图均保留在项目外的 `~/Downloads/Castlevania_build` 或用户数据目录的 `tests` 子目录。

# 星之卡比 新星同盟 4.1.0：原生打包实验记录

**结论：已经打通“提取 → 改写 → 装载 → SDK 启动 → Metal/VI/NVN 窗口 → 读取 RomFS 内容”的打包链路，并生成了一个可双击的实验 App；但还没有进入游戏画面。** 当前在 `nn::account` 的关闭路径上触发 SDK 断言，离“能玩”仍差服务实现、旧版 HID/NVN 语义和逐场景验证。这不是改一个标题 ID 就能完成的事，工作量是“新做一款游戏的移植”。

本记录对应分支 `kirby-experiment`，游戏数据、密钥、构建中间文件和 App 都在项目目录外。

## 输入与识别结果

- 输入：`/Users/duanziyu/Downloads/共享/星之卡比[01007E3006DDA000][4.1.0][中文][US].nsp`
- 标题 ID：`01007E3006DDA000`（Kirby Star Allies 4.1.0）
- ExeFS 模块：`main`、`sdk`、`subsdk0`、`rtld`、`main.npdm`
- SDK 字符串：`NintendoSDK 4.4.1`（`SDK MW+Nintendo`、`FS_ACCESS: { sdk_version: 4.4.1, spec: NX }`）
- NSO 改写：`main` 的 x18/svc 改写通过；`sdk`/`subsdk0` 使用了旧 SDK 的 `ldrsw` 有符号偏移跳转表，原改写器不识别，已补上
- RomFS：3,080,511,292 字节，4,442 个文件，六层 IVFC 校验通过
  - SHA-256：`770bccd2f98dc1a026c63540467657c177ad815b9bf7fdc86f5e65333e4dad9e`

模块 SHA-256（原始 ExeFS）：

| 模块 | Bytes | SHA-256 |
|---|---:|---|
| main | 2,947,812 | `ed4a5c21fdfeed5bcc4352228693a184ec762015b4e19084614c48a68143b3fe` |
| sdk | 4,408,087 | `a1304ee47493b0460187eade706d83b69cb743cdd65f4d12006aef5221c7a82c` |
| subsdk0 | 3,276,012 | `bd33212999e3d72a475d2f44bbbbdfd3f906445b78b54f81199fd1a56f3682a4` |
| rtld | 7,112 | `2cfa67cd7d8a23a013802428e93af6bc4d686a7b6feff85218e23076dfa45201` |

## 已打通的启动阶段

实验运行时 `build-kirby/kirby-native` 的日志依次出现：

1. `nnosInitialize`
2. `nninitInitializeSdkModule`（oe/aoc/pctl/diag 等）
3. `nninitStartup`
4. `main`、`subsdk0`、`sdk` 的 `DT_INIT`，构造器状态均为 2
5. 进入 `nnMain`
6. 打开 `set`、`audren:u`、`prepo:u` 等服务；初始化键盘/手柄/六轴
7. 校验 RomFS，挂载只读资源，读取 `content:/yaml/...`、`mint/`、`msg/`、`snd/` 等大量文件
8. 初始化 Metal 设备、原生 VI display
9. 初始化 NVN 窗口：交换链 2 张，1920×1080，格式 0x38
10. 创建 10 余个 guest 线程，音频渲染线程持续输出（REV4，48 kHz）

之后在 `nn::account::CloseUser` 的 SDK 断言处退出（`sdk+0xb3530`）。此前的另一个崩溃点是 HID 输出缓冲区写入过大导致栈被破坏；已改为不越界写入。现在剩下的不是“文件没放对”，而是旧 SDK 的系统服务/对象语义。

## 实验 App

已在项目目录外生成：

```
/Users/duanziyu/Documents/deepseek-harness/kirby-work/Kirby Star Allies (Experimental).app
```

- 约 2.9 GB，RomFS 以 APFS clone 方式放入
- `Contents/Resources/rewritten/`：改写后的 `main`、`sdk`、`subsdk0`
- `Contents/Resources/romfs/romfs.bin` + `runtime-index.bin`
- `Contents/Resources/fonts/`：固件 22.5.0 的六个共享字体
- `Contents/MacOS/Kirby --check` 返回 `ok: Kirby Star Allies 4.1.0 experimental bundle`
- 直接打开会创建窗口并走到上述断言，**不能游玩**；日志在 `kirby-work/app.log`

## 关键改动

### 1. 旧 SDK 的 NSO 跳转表（`games/totk/third_party/d2r/patch_nso.py`）

新增 `ldrsw_table()` 和 `site_br_targets()`：

- 识别 `ldrsw xT, [xB, xIdx, lsl #2]; add x18, xT, xB; br x18`
- 从 `cmp wIdx, #N; b.hi/b.hs` 得到表项数，从 `adrp`/`add` 得到表基址
- 目标表不连续，不能沿用 TOTK 的“base + 4i 等距落地垫”；改为对每个真实目标生成 `movz/movk + sub + cbz` 分派，并在落地垫恢复 x16/x17
- TOTK 已登记的 `SIGNED_TABLES` 保持原路径，避免改变已验证的 TOTK 输出

### 2. Kirby 编译档案

- `game_version.h` 新增 `KIRBY_GAME` 分支（版本字符串、占位地址）
- `loader.c`：
  - `nn::init::Start` 使用 SDK 4.4 的 4 参数签名
  - Kirby 的构造器状态接受非零（旧 SDK 写 1，TOTK 写 2）
  - 关闭 TOTK 专用崩溃修正、启动检查点和帧控制器补丁
- `game_patches_kirby.c`：`runtime_game_patches` 为空；输出分辨率/帧步进为 no-op
- `world_survey.c`：Kirby 下整块 no-op

### 3. 旧 SDK 服务/ABI 适配

- `ipc.c`：Kirby 下未知服务返回“零成功”的通用会话，先记录命令，避免直接中止
- `fs_host.c`：补 `EnsureSaveData`、`CommitSaveData`、`SetAllocator`、`DeleteDirectory`、`RenameDirectory`
- `input.c`：补 Kirby 用到的 `GetNpadState`、六轴、触摸屏、DebugPad、JoyAssignment、振动等公共入口；不越界写调用方缓冲区
- `applet_host.c`：补 `nn::prepo::Initialize/Finalize`
- `account.c`：补 `OpenPreselectedUser`
- `audio_renderer.c`：REV4 的旧客户端输出不包含 `render_info` 的 16 字节；按 revision 置 0，使输出 8416 字节刚好匹配
- `services.c`：Kirby 音频 `OpenAudioRenderer` 包装以记录事件；`RequestUpdate`/`Execute` 在 `KIRBY_AUDIO_REAL=1` 时走真实 TOTK 渲染器
- `frontend.m`：补 `SetLayerScalingMode`、`CloseDisplay`、`DestroyLayer`、`Finalize`

### 4. NVN 旧版兼容的临时措施

- `hle_nvn.c`：Kirby 下未实现的 NVN 入口记录一次并返回 0，而不是立即中止
- `nvn_mtl.m`：Kirby 的图形池请求 1300 MiB，超过 TOTK 的 1 GiB 零拷贝上限，暂提高到 2 GiB
- 这些是诊断性 fallback，不是正确实现；后续必须逐项补语义，特别是旧的 `nvnDeviceSetIntermediateShaderCache` 和资源布局

## 当前阻塞

1. **`nn::account::CloseUser` 断言**：实验运行时在 `sdk+0xb3530` 触发 `diag::AbortImpl`，调用链来自 `main+0x7950`。已尝试把 `CloseUser` 入口改成 `ret`，断言仍在（说明还有别的对象/服务路径在失败），需要解析 SDK 断言参数或实现 account 服务对象。
2. **旧 HID 结构体布局**：Kirby 的 `GetTouchScreenState<16>`、`GetSixAxisSensorState`、`DebugPadState` 与 TOTK 的尺寸不同；目前不写缓冲区以避免破坏栈，但游戏可能读取到未初始化值。
3. **NVN 旧 ABI**：窗口和命令缓冲已建立，但 110 个未实现入口中有些会被旧游戏调用；`return 0` 只能让流程继续，不能保证资源/句柄正确。
4. **音频事件/线程**：真实 REV4 输出已能持续运行，但旧客户端的完成事件、线程节拍仍需核对；当前启动末段仍有音频相关线程等待。
5. **着色器**：还没有跑通 Kirby 的 NVN 着色器提取/翻译；`totk_xlate` 是针对 TOTK 的 Ryujinx 补丁构建，旧 Maxwell 着色器需要单独验证。

## 复现（当前实验环境）

所有路径都在项目目录外：

```sh
WORK=/Users/duanziyu/Documents/deepseek-harness/kirby-work
PY=/Users/duanziyu/Documents/deepseek-harness/default-workspace/TOTK_build/venv/bin/python
NSP="/Users/duanziyu/Downloads/共享/星之卡比[01007E3006DDA000][4.1.0][中文][US].nsp"
KEYS="/Users/duanziyu/Downloads/共享/prod.keys"
cd "$WORK"

# 1. 提取 ExeFS / RomFS（kirby-work 里的两个小脚本，内部复用项目的提取器）
"$PY" extract_kirby.py "$NSP" "$KEYS" extracted/exefs
"$PY" extract_romfs_kirby.py "$KEYS" extracted/extraction-manifest.json extracted/romfs

# 2. 改写三个模块（需要 venv 里的 capstone/lz4）
for m in sdk subsdk0 main; do
  DM_RULESET=native DM_PRIVATE_GATES=0 "$PY" \
    /Users/duanziyu/Documents/GitHub/MacNativeGames/games/totk/third_party/d2r/patch_nso.py \
    extracted/exefs/$m rewritten2 $m
done

# 3. 生成 runtime_tables.h / romfs_config.h（kirby-work/prepare_runtime_kirby.py）
"$PY" prepare_runtime_kirby.py

# 4. 编译实验运行时
./build_kirby.sh

# 5. 直接跑（无窗口会停在 VI 初始化，这是预期）
KIRBY_AUDIO_REAL=1 TOTK_HEADLESS=1 \
TOTK_ROMFS="$WORK/extracted/romfs" TOTK_ROMFS_PATCHES=0 \
TOTK_SHARED_FONTS="/Users/duanziyu/Documents/deepseek-harness/default-workspace/TOTK_build/totk/extracted/firmware/shared-fonts" \
TOTK_PROFILE_DIR="$WORK/profile" \
./build-kirby/kirby-native rewritten2 boot
```

实验 App 的启动器已经把这些环境变量指向 bundle 内资源；`KIRBY_AUDIO_REAL=1` 必须保留，否则音频更新会被 stub 掉，启动会更早停住。

## 下一步建议

按“先让启动链路稳定，再谈画面”的顺序：

1. 解析 `nn::diag` 断言参数（文件/行/表达式），把 `CloseUser` 的失败点定位到具体对象；为 account 服务补一个真实会话或把旧 SDK 的 account 路径整体旁路。
2. 用 SDK 4.4 的头文件/符号核对 HID 结构体尺寸，补 `GetTouchScreenState`、`GetSixAxisSensorState`、`DebugPadState` 的精确布局。
3. 逐个把 Kirby 实际调用到的 NVN 未实现入口补成语义实现，先保证纹理/缓冲/命令缓冲/窗口生命周期正确，再看着色器。
4. 用 `TOTK_HLE_TRACE=1`、`TOTK_FS_LOG=1`、`TOTK_DUMP_AFTER=8` 继续定位线程等待；这三个开关只影响诊断，不改变游戏数据。
5. 通过后再做首帧、标题画面、存档、音频和性能测试；当前不能声称“可玩”或“稳定”。

## 边界

- 仓库不含游戏、密钥、字体或存档；实验 App 和中间文件都在项目目录外。
- 本实验只针对用户自己的 4.1.0 中文 NSP，未验证其他版本、DLC、其他区域或其他游戏。
- `kirby-experiment` 分支上的改动是实验性的；TOTK 的已验证路径应继续用原有默认编译（不加 `KIRBY_GAME`）。

## 2026-10-19 继续推进：到达 Movie.Scene

上一版停在 account 断言。之后补了 `nn::account::OpenPreselectedUser` 的主机重定向，并让旧 SDK 的 `nv::mm` 分配器拿到原始回调（`gfx_bridge.c`），启动链继续前进：

1. 通过 account 打开/关闭
2. 初始化着色器缓存，启动原生 `totk_xlate` 服务
3. 建立 NVN 交换链，开始以 60 fps 出帧（`window visible ... frame 100+`）
4. 加载 `content:/mov/Product/ImageMovie.mp4`（1920×1080 H.264 / 44.1→48 kHz AAC，46.2 秒）
5. 进入 `Movie.Scene`，创建视频/音频 `movie::Decoder`
6. 用 `KIRBY_MOVIE_FILE` 指向预先解码的 NV12 帧后，视频解码器能返回第 0 帧

目前卡在 **Movie.Scene 的 Mint 异常**：`Movie.Scene.initAsync` 线程在拿到第一帧后仍会 `svcBreak`，Mint 侧没有继续到标题场景；画面仍是黑色。视频/音频 Extractor 对 MP4 返回 EOS（`send_input size=0 flags=EOS`），说明旧 SDK 的 MP4 解复用还没有在宿主上跑通。为了继续，试过把 `mint/Seq.bin` 的 `MovieOpening` 改成 `Finished`，游戏仍进入 Movie.Scene，说明序列状态不是按这个字符串直接选路的。

当前可复现的实验命令（`kirby-work` 内）：

```sh
# 预先解码开场影片为 NV12 帧（4.0 GB，30 fps，1385 帧）
ffmpeg -i ImageMovie.mp4 -an -vf scale=1920:1080 -pix_fmt nv12 -f rawvideo -y ImageMovie.nv12

KIRBY_MOVIE_FILE="$PWD/ImageMovie.nv12" \
KIRBY_AUDIO_REAL=1 TOTK_SHADER_SERVICE=native \
TOTK_ROMFS="$PWD/extracted/romfs" TOTK_ROMFS_PATCHES=0 \
TOTK_SHARED_FONTS="/Users/duanziyu/Documents/deepseek-harness/default-workspace/TOTK_build/totk/extracted/firmware/shared-fonts" \
TOTK_PROFILE_DIR="$PWD/profile" \
./build-kirby/kirby-native rewritten2 boot
```

- `KIRBY_MOVIE_FILE` 不存在时退回真正的黑帧/静音 stub，不再走 NvMM。
- `KIRBY_TRAP_PROBE=1` 会在第一个 SDK abort trap 打印 x0..x7 并退出，用于定位 Mint 异常。
- `TOTK_TRAP_PROBE` 不是正式开关，只用于诊断。

**下一处最小工作**：让 Movie.Scene 的 Mint 脚本不再异常。方向有两个：实现旧 SDK 的 MP4 Extractor/MediaData（让 `send_input` 真正拿到 H.264 样本），或者从 `mint/Seq.bin`/存档层跳过 `MovieOpening`。在此之前，程序能持续出帧，但不会进入标题菜单。

### 第一次真正出画：必须显式允许 GPU 提交

黑屏的一个关键原因不是解码器，而是宿主的保护开关：

```text
[dm] [nvn-mtl] 【红】GPU submission disabled: work is encoded but never submitted
(no picture, no GPU results); TOTK_GPU_ALLOW_SUBMIT=1 re-enables it
```

设置 `TOTK_GPU_ALLOW_SUBMIT=1` 后，GPU 开始执行命令，帧率约 60 fps，GPU 时间约 0.16 ms；用运行时截图命令在 `F310` 抓到了第一张有内容的画面（黑色背景、右下角粉色 Kirby 标志）。这说明 NVN→Metal 的绘制/提交链路已经真正工作，不再只是“录制命令”。

实验 App 的启动器已经加入：

```sh
export TOTK_GPU_ALLOW_SUBMIT=1
export KIRBY_MOVIE_FILE="$HERE/Resources/movie-head.nv12"   # 影片前 3 帧，约 8.9 MB
```

因此双击 App 至少能看到这张开场影片画面，而不是纯黑。`Movie.Scene` 仍会在第一帧后触发 Mint 异常，标题画面尚未到达。

### 2026-10-19 第二轮：Movie.Scene 的断言不在取帧之后

这一轮继续拆 `Movie.Scene` 的 abort，结论是它**不是**“等不到视频帧”：

- 视频 stub 已经返回第 0 帧（`stub video frame 0/1385`），并把输出标记为 held。
- 音频输出补了 `pcm-encoding` / `channel-mask`，不再立即 EOS。
- 把 SDK abort trap 末尾的 `b .` 改成 `ret`，让断言线程能返回。
- 但日志里**从未出现 `stub get_output` 或 `stub release_output`**：游戏在 `AcquireOutputBufferIndex` 之后就直接在 `Movie.Scene.initAsync` 断言，根本没走到取帧/释放帧。

因此下一个最小点不是继续调 NV12 拷贝，而是：

1. 让旧 SDK 的 MP4 Extractor 返回真实样本，使 Movie.Scene 的 Mint 状态正常结束；或
2. 在 Mint 序列/场景创建层跳过 `MovieOpening`。

在这之前，App 只能显示已抓到的第一张开场帧，不能进入标题。

### 第三轮：断言来自 Mint VM，而不是解码器

用 `KIRBY_TRAP_PROBE=1` 打印 abort trap 的 x0..x7 和寄存器指向的内存，x7 指向的是一段 Mint 运行时字符串：

```text
x7 bytes: 69 6f 6e 73 41 6e 64 45 72 72 6f 72 73 53 6f 6f 6e 00 ...
x7 str:  ionsAndErrorsSoon
```

前面 7 个字节被截掉，完整形态应是 `ExceptionsAndErrorsSoon` 一类的 Mint 异常类型名。结合“`GetOutputBuffer` 未被调用”这一事实，可以把原因归为：

- 视频 stub 已返回第 0 帧；
- 但 `Movie.Scene` 的 Mint 状态机在取帧/释放帧之前就抛出了异常；
- 所以继续调 NV12 拷贝或音频字段不会推进场景。

下一步应该直接处理 Mint 异常/场景创建，而不是继续补 movie decoder 的输出格式。

### 第四轮：异常表落在 sdk 的 Mint 数据区

继续用 `KIRBY_TRAP_PROBE=1` 打印 abort trap 的 x2 指针（疑似 Mint 异常/类型表），前 16 个 8 字节值全部落在 `sdk` 的 **数据区**：

```text
x2[0]  0x...a000  sdk+0x942000
x2[1]  0x...f7c1  sdk+0x7977c1
x2[2]  0x...f7d7  sdk+0x7977d7
...
```

`sdk` 的 `TEXT_END` 是 `0x40e8b0`，`0x7977c1` 已经远超代码段，说明这不是调用栈，而是 Mint VM 的**类型/异常表**。结合 `ExceptionsAndErrorsSoon` 一类的字符串，可以确认：Movie.Scene 的停止点是 **sdk 内 Mint VM 的脚本异常**，不是 main 或 movie decoder 的崩溃。

这进一步说明：
- 继续补 `movie::Decoder` 的 NV12/音频字段不会推进；
- 需要从 Mint 脚本/序列层跳过 `MovieOpening`，或让 Mint VM 把该异常视为可恢复。

### 第五轮：原始 decoder / 重封装 / 按住跳过 都不改变 Movie.Scene

- `TOTK_MOVIE_HOST=0` 走 SDK 原始 NvMM decoder：仍停在 Movie.Scene，45 秒后没有标题。
- 把原片重新 remux（去 edit list、mp42、faststart）：Extractor 仍 `size=0 EOS`。
- 从启动就按住 `+`/`A`（`down 36` / `down 38`）：仍进 Movie.Scene。
- 把 `sdk+0x452c4`（diag translate）入口改成 `ret`：仍断言，场景不变。
- 这一步说明：Movie.Scene 的 Mint 异常不依赖具体 decoder、容器或按键时序；必须在 Mint 序列/异常处理层处理。

### 第六轮：所有 Npad 状态都返回按键，仍不能跳过

为了排除“Movie.Scene 轮询的是 JoyDual/Handheld 状态，因此看不到 A/+”这一可能，Kirby profile 下让所有 `GetNpadState` 变体都返回同一份键盘/手柄状态，并从启动就按住 `+`、`A`、`B`：

```text
[file: key 36 down][file: key 38 down][file: key 40 down]
```

结果仍进入 Movie.Scene 并断言。输入不是 Movie.Scene 的阻塞点；影片/Mint 场景的失败发生在轮询按键之前。

### 用 Ryujinx 存档跳过 Movie.Scene

用户选择先用通用模拟器生成一份“已看过开场、能进标题”的存档。仓库新增
`games/kirby/tools/import_ryujinx_save.py`：它从 Ryujinx 的
`bis/user/save/.../01007E3006DDA000` 找到存档，备份原生 profile 的现有存档，
再把文件复制到当前唯一的 save slot。

Ryujinx 的 macOS 存档通常在：

```text
~/Library/Application Support/Ryujinx/bis/user/save/0000000000000000/01007E3006DDA000
```

导入命令：

```sh
python3 games/kirby/tools/import_ryujinx_save.py \
  --ryujinx-save "$HOME/Library/Application Support/Ryujinx/bis/user/save" \
  --profile /Users/duanziyu/Documents/deepseek-harness/kirby-work/profile
```

当前环境无法稳定连接到 Ryujinx 的更新服务器，下载/安装需要用户在本机完成；
拿到存档后就可以直接验证跳过 Movie.Scene 后的标题、菜单和第一关。

### 第七轮：开始直接检查 guest 内存里的 Mint 模块

新增 Kirby 专用诊断命令（`TOTK_INPUT_FILE`）：

```text
scan <ascii>                 在 guest 内存中搜索 ASCII 字符串
scanptr <value> [start end]  搜索 8 字节指针
dump <addr> <len>            hex dump
```

实测在 `Movie.Scene` 阶段：

- `scan MovieOpening` 找到堆上的字符串表 `0x3dc522d80`，内容正是：

```text
MovieOpening / ExecChildSeq / Finished / XBIN4 ...
```

- `scanptr 0x3dc522d80` 在附近 32 MB 内没有找到直接指针，说明 Mint 代码使用的是模块内偏移/哈希，而不是保存绝对字符串地址。
- `scan XBIN4` 显示 RomFS 里的模块被加载到 `0x334800000` 一带；`Default.bin` 等大模块和堆上的脚本副本是分开的。

这说明下一步可以沿“找到包含 MovieOpening 的 Mint 模块基址 → 解析模块的类/函数表”走，而不是继续猜 decoder。

### 第八轮：定位到 Seq.bin 的 guest 模块基址

`scandump MovieOpening` 同时完成了扫描和 dump，确认加载后的 `Seq.bin` 模块基址：

```text
base = 0x3dc520000
+0x3d80  MovieOpening / ExecChildSeq / Finished 字符串表
```

模块头是完整的 `XBIN4 12 02 00 00 d5 3b 01 00 ...`，大小与 RomFS 里的 `mint/Seq.bin` 一致。

新增 `pokeat <needle> <delta> <hex>`：找到字符串后可直接改 guest 内存。实测把 `MovieOpening` 的长度前缀改成 8、内容改成 `Finished`（一次写 16 字节）后，**场景仍停在 Movie.Scene**。这说明 Mint VM 用的是模块内的函数/状态索引，而不是运行时按这个字符串重新查函数。

下一步应解析模块头 0x30 起的类/函数描述表，找到状态函数索引，而不是继续改字符串。

### 第九轮：找到 SequenceStoryMode 的类描述，但没找到状态代码入口

在 `Seq.bin` 文件偏移 0x3b70 找到 `Seq.SequenceStoryMode` 的类描述区，包含：

```text
Seq.SequenceStoryMode
mPhase            // 类型 Seq.SequenceStoryMode.Phase
mIsWatchMovie     // bool
void this()
nextAction()
createChildSequence()
onChildSequenceEnd(...)
createScene()
onSceneEnd(...)
onEnd()
MovieOpening / ExecChildSeq / Finished
```

0x750 起的表又引用了 0x350、0x560 等偏移，但这些偏移落在**属性/方法名字符串区**，不是 AArch64 代码，也不是可直接改的函数指针。`MovieOpening` 等状态更可能是 Mint 字节码里的入口，而不是一个 C++ 虚表槽。

因此：

- 已确认模块基址、类描述、状态名和 `mPhase`/`mIsWatchMovie` 字段；
- 但还没有把 `MovieOpening` 映射到具体字节码地址；
- 直接改字符串/长度已证明无效。

下一步要么解析 XBIN4 的字节码/方法表，要么用一份已进标题的存档绕过 Movie.Scene。

### 第十轮：把扫描范围扩到低地址模块区

之前的内存扫描从 `0x300000000` 开始，漏掉了加载在低地址的 `main`/`sdk`/`subsdk0`。现在 `scan`/`scanptrat` 默认从 `0x100000000` 开始，并新增：

```text
scanword <hex> [start end]       搜索 4 字节值
scanptrat <needle> <delta>       找到字符串后搜索指向 hit+delta 的 8 字节指针
```

实测 `scanptrat Seq.SequenceStoryMode 0` 在低地址找到字符串，但第一次命中的是输入命令缓冲区本身（`0x10478752a`），指针命中也是输入线程栈；需要先排除这类诊断缓冲区，或直接在 `main` 模块的 `0x394aa2` 地址附近做 `scanr`。

这也说明 `main` 里确实有 `Seq.SequenceStoryMode` 的类型名字符串；下一步可以沿 RTTI/typeinfo 的 RELR 重定位找 vtable，再找活对象，而不是继续扫整个 guest。

### 第十一轮：HLE trace 显示 Movie.Scene 在 audout:u 之后断言

打开 `TOTK_HLE_TRACE=1` 后，Movie.Scene 失败前的最后调用是：

```text
h=0x100c movie::Decoder::GetOutputFormat(...)
[kirby-ipc] opened generic service audout:u
[kirby-ipc] audout:u command 1 (type 4, data 32) -> zero success
[totk] guest Break
```

也就是说：视频第 0 帧之后，游戏去打开 **audout:u**，通用 IPC 回了零成功，随后 Mint 场景断言。

已在 `ipc.c` 增加最小 `audout:u` / `IAudioOut` 服务：

- `OpenAudioOut` 返回 `IAudioOut` 会话句柄和 `AudioOutParameterInternal`（48000/2ch/PcmInt16/Stopped）
- `IAudioOut` 的 Append/RegisterBufferEvent/GetReleased/State/Volume 等命令返回成功
- 可用 `KIRBY_AUDOUT_FAIL` / `KIRBY_AUDOUT_APPEND_FAIL` 注入失败做对照

结果：

- `OpenAudioOut` 通过，游戏开始调用 `IAudioOut` cmd 7（AppendAudioOutBufferAuto）4 次，随后在 sdk 的 guest `memcpy` 处 SIGBUS；
- 注入 append 失败后不再 SIGBUS，但又回到原来的 `Movie.Scene.initAsync` Mint 断言。

这确认 Movie.Scene 的异常与 **音频输出路径** 强相关，而不是单纯的视频帧或 `MovieOpening` 字符串。下一步应让 `AppendAudioOutBufferAuto` 正确回收/释放音频缓冲，避免 SDK 音频线程读坏指针。

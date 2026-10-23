# 通用输入检查矩阵（2026-10-23）

使用 `python3 build_game.py inspect GAME --keys PROD.KEYS` 对项目外原始输入逐个运行；恶魔城组合 XCI 的主游戏另加 `--title-id 0100BA4026E94000`。只读检查器临时提取 ExeFS，验证容器、ExeFS 与已提供的 NSO 段哈希，分析模块和静态导入，然后删除临时提取目录。原始游戏和密钥未复制到源码项目。

| 输入 | 报告状态 | Program 身份 | NSO 模块 | `main` 静态导入数 |
|---|---|---|---:|---:|
| 王国之泪本体 NSP | `known_title_unknown_version`；代码匹配固定 1.0.0，但 `main.npdm` 不同 | 基础版 `0100F2C0115B6000` | 4 | 674 |
| 卡比本体 NSP | `known_title_unknown_version` | 基础版 `01007E3006DDA000` | 4 | 574 |
| 恶魔城组合 XCI 的主游戏 | `known_title_unknown_version` | 基础版 `0100BA4026E94000` | 4 | 715 |
| 恶魔城独立更新 NSP | `known_title_unknown_version` | 更新档，基础 ID `0100BA4026E94000` | 4 | 717 |
| 马里奥惊奇本体 NSP | `unported_title` | 基础版 `010015100B514000` | 3 | 1,107 |
| 马里奥惊奇独立更新 NSP | `unported_title` | 更新档，基础 ID `010015100B514000` | 3 | 1,135 |

六份输入的容器头、ExeFS 哈希链与 NSO 段哈希检查均通过。原始输入在 `~/Downloads/共享/`，小型 JSON 报告依次保存在 `/tmp/mng-inspect-totk-final-20261023.json`、`/tmp/mng-multigame-kirby-20261023.json`、`/tmp/mng-multigame-castlevania-base-20261023.json`、`/tmp/mng-multigame-castlevania-update-20261023.json`、`/tmp/mng-inspect-final-base-20261023.json`、`/tmp/mng-inspect-final-update-20261023.json`。这些 `/tmp` 文件可能被系统清理，可从原始输入重跑。

随后用完整 `inspect` 命令对同一批原始输入重新运行，六份报告的 `cnmt_hash_chain` 均为 `pass`：四份本体原始版本整数均为 `0`，恶魔城更新包为 `65536`（`0x10000`），马里奥更新包为 `327680`（`0x50000`）。两份更新包的内容类型均为 `patch`。这些整数来自哈希校验通过的元数据，不等于文件名所写的语义显示版本。新版六份 JSON 均位于 `/tmp/mng-cnmt-<输入名>-20261023.json`，其中输入名依次为 `totk`、`kirby`、`castlevania-base`、`castlevania-update`、`mario-base`、`mario-update`。

把离线工具实现迁至 `game_tools/` 后，再次运行马里奥本体/更新包、卡比本体和恶魔城组合 XCI 主游戏；四份检查均保持原状态，CNMT 与 ExeFS 哈希链仍为 `pass`。复验 JSON 在 `/tmp/mng-shared-tools-<输入名>-20261023.json`，输入名为 `mario-base`、`mario-update`、`kirby`、`castlevania-base`。

共用 ExeFS 命令现要求显式 `--title-id`，王国之泪旧脚本路径保留原默认值。用该共用命令对马里奥本体和升级档再次提取，`main` SHA-256 分别保持 `f197aa237cb7de76888bc29077796fb85eb2bad5b762e15d26d48789bdfe0dbb` 和 `ff9a3728246d45a750a686d1625bdeafb0a361ea75e19964675a14f629f98c32`；临时 ExeFS 已清理。

共用 RomFS 命令不再默认读取王国之泪清单或向相对的 `extracted/v0/romfs` 写入；本体需要显式清单和输出目录，DLC 需要显式源、title ID 与输出目录。旧王国之泪入口保留既有默认值。用新共用命令对马里奥本体重跑，六层 IVFC、3,726,437,684 字节、19,012 个文件及 RomFS SHA-256 `93f395acc2cb55ab2b7a9ad9b74a39a797f3e82483d7fedc85a3bc229baf8aab` 再次一致，临时数据已清理。

RomFS 共用工具又对马里奥本体 NSP 单独完成六层 IVFC 校验和文件索引：3,726,437,684 字节、19,012 个文件，SHA-256 `93f395acc2cb55ab2b7a9ad9b74a39a797f3e82483d7fedc85a3bc229baf8aab`。固定 hactool 对本体和升级档的 BKTR 合并也通过六层 IVFC 校验：3,732,302,808 字节、19,034 个文件，SHA-256 `e68e6b26c3d4edbdc879a54edcaf70c0be7877d881eb41a42cfcdb1d3b8d328b`。大型临时输出已清理，摘要位于 `/tmp/mng-mario-romfs-proof-20261023.json` 与 `/tmp/mng-mario-bktr-fixed-proof-20261023.json`。这些结果不改变 `inspect` 的 `romfs: not_assessed` 字段，也不证明原生运行。

BKTR 合并实现现位于 `game_tools/extract_update_romfs.py`；共用命令必须传基础游戏 `--title-id`，王国之泪原路径保留既有默认 ID。新共用命令也对马里奥原始输入完成真实复验，结果与迁移前一致；小型摘要在 `/tmp/mng-mario-shared-bktr-proof-20261023.json`。迁移只改变离线工具调用路径，不改变合并、IVFC 校验或游戏运行热路径。

`build_game.py inspect BASE --update UPDATE --keys PROD.KEYS` 现可在合并前核对本体与独立升级档的角色、同一基础 title ID 和各自的代码检查结果。用马里奥两份原始 NSP 运行，配对身份通过，title ID 为 `010015100B514000`，两份 CNMT 哈希链均通过；两份支持状态仍均为 `unported_title`。只读 JSON 在项目外 `/tmp/mng-mario-paired-inspect-20261023.json`，不证明升级档已可构建或运行。

共用 NSO 改写探针按实际模块集合处理马里奥本体的 `rtld`、`main`、`sdk`，不要求 `subsdk0`。它核对原 ExeFS 清单的大小与哈希，强制关掉游戏私有规则并拒绝定点补丁记录；三模块均成功且定点记录为零。摘要在 `/tmp/mng-mario-shared-rewrite-proof-20261023.json`，大型改写输出已清理。此项只证明指令改写阶段可复用，不证明装载、服务语义或原生运行。

共用静态装载前检查又对马里奥本体 `main/sdk` 的动态符号、重定位类型/边界及宿主门完成验证；`rtld` 按现有原生装载器约定单列排除。两模块共 404,432 条重定位，原始表合计 9,706,368 字节；若沿用已有游戏脚本生成平铺 C 表，会再增加约 9.7 MB 重复数据。摘要在 `/tmp/mng-mario-runtime-preflight-proof-20261023.json`，大型临时表已清理。静态解析不证明符号绑定、构造器、服务、NVN 或性能可用。

共用 C 读取器对马里奥本体两模块的原始 RELA/PLT 表又完成逐条对拍：总数、类型分布及顺序校验值与 Python 静态表一致；源表均在只读段，满足边遍历边向数据段写入的基本条件。七轮纯内存遍历的样本计时记录于 `/tmp/mng-mario-reloc-stream-proof-20261023.json`；它不含真正的重定位写入及启动过程，不能说明 App 启动或帧率已改善。大型临时映像与测试二进制均已清理。

共用写入核心随后以固定测试符号地址对同一批已验证的 `main/sdk` 执行所有 404,432 条重定位，分别与独立平铺表 C 循环逐字节比较整个映像，七轮均一致。热轮次最短耗时合计：流式约 1.183 毫秒，平铺约 0.570 毫秒；若未来采用流式路径，可省去约 9.7 MB 的额外平铺表。两条离线写入路径相差约 0.6 毫秒，包含回调和检查开销，未计入表加载或真实 App 启动。摘要在 `/tmp/mng-mario-reloc-apply-proof-20261023.json`；这里的合成符号地址不代表宿主绑定、服务或帧时间验证。

另一个标称“恶魔城本体 1.1.0”的独立 NSP 被 NCA3 区段边界校验拒绝：Program NCA 的容器条目及 NCA 头大小均为 558,891,008 字节，而头内区段结束位置达到 3,058,843,648 字节。不能把它当作已验证的标准 NSP，也不能仅凭此断定游戏版本本身有问题；本次矩阵使用通过检查的组合 XCI 本体和独立更新 NSP。

导入数是 `main` 中的静态符号数量，不能推断运行路径、ABI 兼容性或宿主服务覆盖率。`known_title_unknown_version` 也不表示原始输入可直接构建：卡比和恶魔城的现有工作流仍需项目外已验证宿主或工作目录。六份 `inspect` 报告没有检查 RomFS；单独的马里奥本体 RomFS 验证如上。NCA RSA 签名、运行时服务、NVN 实际着色器阶段、启动画面或帧时间尚未检查；这些需要后续实机验证。

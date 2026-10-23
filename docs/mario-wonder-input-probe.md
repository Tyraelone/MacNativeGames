# 《超级马里奥兄弟 惊奇》输入样本：2026-10-23

这是一份通用化流程的第四个**未移植**测试样本。原始本体与升级档仍在 `~/Downloads/共享/超级马里奥兄弟 惊奇 Super Mario Bros. Wonder/`；本次读取未改动它们，也未把游戏数据放进源码目录。文件名标称本体 1.0.0、升级档 1.2.1；后续读取了 CNMT 原始版本整数，但它不等同于文件名中的显示版本。

两份原始 NSP 的 SHA-256 分别为本体 `fc6468c7c1aab1d7cafc2638fb9c968a22fc8e6d020c282fc19df2fdb78e71ac`、升级档 `f195eaae2b7b48bb9dfe2101d2a9a62142e1fc9642f23a58779c6efddcf51608`。

| 输入 | 内部身份与结构 | 已验证的代码摘要 |
|---|---|---|
| 本体 NSP | NCA title ID `010015100B514000`；一个 Program NCA；ExeFS 约 32.7 MiB | ExeFS 完整哈希链通过；`main` SHA-256 `f197aa237cb7de76888bc29077796fb85eb2bad5b762e15d26d48789bdfe0dbb`；build ID `cd6e42aee7934f4d8393cd43893ae25edc83d338000000000000000000000000` |
| 升级档 NSP | Program NCA 保持基础 title ID；元数据使用 `010015100B514800`；ExeFS 约 33.7 MiB，另有 BKTR RomFS 区段 | ExeFS 完整哈希链通过；`main` SHA-256 `ff9a3728246d45a750a686d1625bdeafb0a361ea75e19964675a14f629f98c32`；build ID `ff773e90972d544eb79406eaa65396d53c43efb9000000000000000000000000` |

两份 ExeFS 均只有 `rtld`、`main`、`sdk` 三个 NSO，没有 `subsdk0`。三者的 NSO 段哈希与动态符号表盘点均通过。基础版 `main` 有 1,107 个导入，升级档有 1,135 个；按同包模块的符号名称分别找到 1,093 与 1,121 个候选定义。升级档盘点中新增 `nn::aoc`、`nn::ec`、`nn::nfp` 等导入分组。这些是静态链接线索，不证明调用会发生、宿主实现了对应语义，或 ABI 已兼容。

这个样本暴露了原 `prepare_modules.py` 和 `map_dependencies.py` 固定要求 `subsdk0` 的假设。现改为盘点实际 NSO，并从生成的 `modules.json` 读取依赖图模块集合；王国之泪仍会包含其 `subsdk0`。马里奥本体与升级档都通过了这两步。临时 ExeFS、ELF 和盘点输出位于项目外 `/tmp/mng-mario-probe-20261023.8fLZdV/`，可从上述原始 NSP 重新生成；它们不是项目依赖。

尚未验证：游戏服务调用、NVN 着色器阶段、指令改写、启动、画面和帧时间。现有正式构建器仍按王国之泪的版本哈希、模块列表和资源规则工作；它不能把本样本直接打包为受支持的 App。ExeFS 提取器验证了 FS header、ExeFS 哈希表与每个 ExeFS 数据块，没有验证 RSA 签名。

统一只读入口 `build_game.py inspect <NSP> --keys <prod.keys>` 已对本体和升级档实际运行。两者均报告 `unported_title`、模块 `rtld/main/sdk`；容器头、ExeFS 哈希链、NSO 段哈希为 `pass`，RomFS、宿主服务、NVN、媒体、改写、游玩性能为 `not_assessed`。小型 JSON 报告保存在项目外 `/tmp/mng-mario-probe-20261023.8fLZdV/{base,update}/inspect-report.json`；检查器的独立临时工作目录已自动清理。同一入口在已有王国之泪本体 NSP 上发现四个 NSO 均匹配固定 1.0.0 代码，但 `main.npdm` 不同，因此报告 `known_title_unknown_version` 与 `code_match`，没有把该包误报为完整的固定配置。

后续直接解析经哈希验证的 CNMT：本体的原始版本值为 `0`，升级档为 `327680`（`0x50000`），内容类型分别为 `application`、`patch`。这些是内部整数，不能据此宣称文件名中的“1.2.1”已获独立证明。新版报告示例在项目外 `/tmp/mng-inspect-mario-cnmt-20261023.json`。

将 RomFS 提取与索引移到共用工具后，对本体 NSP 另作项目外的真实验证：FS header 和六层 IVFC 均通过，RomFS 大小 3,726,437,684 字节、SHA-256 为 `93f395acc2cb55ab2b7a9ad9b74a39a797f3e82483d7fedc85a3bc229baf8aab`，索引到 19,012 个文件。本次耗时约 5.68 秒，仅是这台机器对该输入的一次离线提取测量，不是游戏帧时间。完整 RomFS 临时文件已清理；小型摘要保存在 `/tmp/mng-mario-romfs-proof-20261023.json`，系统可能清理该临时证据。`inspect` 报告仍将 RomFS 标为 `not_assessed`，因为它不执行大型提取。

随后用项目固定提交的 hactool 和原始本体、升级档、`prod.keys` 运行 BKTR 合并。hactool 对原始密钥文件中无关但长度不合其格式的项报错；构建脚本现将它需要的有效 NCA 密钥类别写入权限为 `0600` 的项目外临时文件，并在合并后清理。使用原始 `prod.keys` 重跑，BKTR 和六层 IVFC 均通过：合并 RomFS 为 3,732,302,808 字节、19,034 个文件，SHA-256 `e68e6b26c3d4edbdc879a54edcaf70c0be7877d881eb41a42cfcdb1d3b8d328b`。该结果与先前手工筛选密钥的独立运行一致；大型临时输出已清理，摘要位于 `/tmp/mng-mario-bktr-fixed-proof-20261023.json`。本机验证使用 Xcode 26.5 SDK；系统默认的命令行工具 SDK 在链接 hactool 时失败。此验证仍不证明马里奥可原生运行。

BKTR 合并器移到 `game_tools/` 后，以要求显式 `--title-id 010015100B514000` 的新共用命令和同一批原始输入再次完整运行。固定 hactool 的构建及合并共耗时约 47.2 秒；六层 IVFC、3,732,302,808 字节、19,034 个文件和上述 SHA-256 再次一致。临时 hactool、合并输出和密钥文件均已清理，仅保留小型摘要 `/tmp/mng-mario-shared-bktr-proof-20261023.json`。该时间是一次离线工具运行，不是游戏启动或帧时间。

现有 ARM64 改写器对本体 ExeFS 的 `rtld`、`main`、`sdk` 三个 NSO 都完成了指令改写。随后共用 `game_tools/rewrite_modules.py` 先逐一比对提取清单的大小和 SHA-256，再复验相同三模块；`rtld`、`sdk` 分别登记 4、100 个宿主门，`main` 为 0，三者的定点剪口、参数改写和观测门均为 0。大型改写结果在项目外临时目录验证后已清理，小型摘要位于 `/tmp/mng-mario-shared-rewrite-proof-20261023.json`。这个结果仅说明现有改写器能处理该批指令；尚未生成通用装载表，也未验证重定位、宿主服务、NVN、启动或帧时间。

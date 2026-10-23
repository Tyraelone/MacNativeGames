# 游戏输入只读检查器

## 目的

在尝试移植或打包前，用同一入口报告任意单游戏 XCI/NSP 的内部 title ID、基础版/升级档身份、经过完整 ExeFS 哈希验证的代码模块，以及静态依赖线索。报告必须将已固定的代码版本与仅识别到游戏 title 的输入区分开，不能把静态导入推断为宿主支持，也不能把文件名当作版本证明。

## 接口

`python3 build_game.py inspect GAME --keys PROD.KEYS [--title-id HEX]` 输出一个 JSON 对象。`--title-id` 在组合 XCI 有多个 Program 时用于明确选择本体 Program；不选择则报错。含多个 Program 的组合更新 XCI 不支持，应使用独立更新 NSP。升级档按 Program NCA 的 BKTR 区段识别，其 Program 可保持基础 title ID；元数据 title ID 应为基础 ID 加 `0x800`。本次只检查一个包，不合并 RomFS，也不推断升级档与某个本体文件能配对。

检查器复用现有容器读取器、ExeFS 提取器、NSO 段验证器和依赖图工具。提取与合成 ELF 只写系统临时目录，调用完成即删除；原始游戏文件与密钥只读取，源码目录无产物。输出只含标题/模块身份、哈希、静态导入分组和状态，不含密钥、解包字节或原始符号列表。

## 状态与信任边界

与王国之泪 `expected-v*.json` 的整套 ExeFS 文件哈希完全匹配时，标记 `verified_exefs_profile` 并返回版本。已登记 title ID 但未匹配完整哈希时标记 `known_title_unknown_version`；若全部 NSO 代码哈希唯一匹配某个版本、但 `main.npdm` 不同，另列 `code_match` 与不匹配文件名，仍不升格为已支持。其他 title 标记 `unported_title`。卡比和恶魔城现有打包仍需要项目外已验证的宿主，本阶段不把它们的原始 NSP 自动升级成正式构建输入。三种状态都不表示 RomFS、服务、NVN、媒体、指令改写或实机帧时间已经通过。

报告分列 `container_header`、`exefs_hash_chain`、`nso_segment_hashes` 的验证状态。NSO 段哈希可为 `pass`、`partial` 或 `not_present`，每个模块单列是否验证；NCA RSA 签名标记 `not_checked`。`romfs`、`host_services`、`nvn`、`media`、`rewrites`、`gameplay_performance` 均标记未评估。静态导入按分组计数，并注明它只是名称候选，不是调用或 ABI 证明。失败的输入不能产生成功报告；退出码非零且不留下临时目录。

## 验证

合成容器测试覆盖无猜测的 title 选择、升级档身份、未知版本与确切哈希匹配；CLI 测试覆盖参数转交和临时目录约束。完整测试集须通过。马里奥本体与升级档作为项目外真实样本运行检查器：预计均为 `unported_title`，各列出 `rtld/main/sdk`，且报告不会因 `subsdk0` 缺失失败。性能影响限于离线检查器，不进入游戏进程。

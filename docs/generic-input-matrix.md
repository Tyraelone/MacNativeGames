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

RomFS 共用工具又对马里奥本体 NSP 单独完成六层 IVFC 校验和文件索引：3,726,437,684 字节、19,012 个文件，SHA-256 `93f395acc2cb55ab2b7a9ad9b74a39a797f3e82483d7fedc85a3bc229baf8aab`。固定 hactool 对本体和升级档的 BKTR 合并也通过六层 IVFC 校验：3,732,302,808 字节、19,034 个文件，SHA-256 `e68e6b26c3d4edbdc879a54edcaf70c0be7877d881eb41a42cfcdb1d3b8d328b`。大型临时输出已清理，摘要位于 `/tmp/mng-mario-romfs-proof-20261023.json` 与 `/tmp/mng-mario-bktr-fixed-proof-20261023.json`。这些结果不改变 `inspect` 的 `romfs: not_assessed` 字段，也不证明原生运行。

另一个标称“恶魔城本体 1.1.0”的独立 NSP 被 NCA3 区段边界校验拒绝：Program NCA 的容器条目及 NCA 头大小均为 558,891,008 字节，而头内区段结束位置达到 3,058,843,648 字节。不能把它当作已验证的标准 NSP，也不能仅凭此断定游戏版本本身有问题；本次矩阵使用通过检查的组合 XCI 本体和独立更新 NSP。

导入数是 `main` 中的静态符号数量，不能推断运行路径、ABI 兼容性或宿主服务覆盖率。`known_title_unknown_version` 也不表示原始输入可直接构建：卡比和恶魔城的现有工作流仍需项目外已验证宿主或工作目录。六份 `inspect` 报告没有检查 RomFS；单独的马里奥本体 RomFS 验证如上。NCA RSA 签名、运行时服务、NVN 实际着色器阶段、启动画面或帧时间尚未检查；这些需要后续实机验证。

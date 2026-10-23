# 共用升级档 RomFS 合并工具设计

## 目标

把已用《王国之泪》和《超级马力欧兄弟 惊奇》真实输入验证的 BKTR/IVFC 合并实现放入 `game_tools/`。共用命令对基础游戏 title ID 采用显式参数，旧《王国之泪》命令保持现有默认值和调用方式。此工具只生产离线验证产物，不宣称新游戏已经可以原生运行。

## 接口和边界

- `python3 game_tools/extract_update_romfs.py BASE UPDATE --keys PROD.KEYS --hactool HACTOOL --title-id HEX --output EXTERNAL_DIR`：共用入口必须传 16 位基础游戏 title ID。
- `game_tools.extract_update_romfs.merge(..., title_id=HEX)`：程序接口也必须显式传入 title ID；合并前检查格式，并使用既有容器与 Program 身份校验。
- `games/totk/scripts/extract_update_romfs.py`：保留原命令和 `merge` 函数，省略 title ID 时仍使用 `0100F2C0115B6000`，显式提供时继续允许其他目标。
- 共用实现仍在项目外输出；临时 NCA、私有密钥文件和失败清理遵循现有行为。只移动一份实现，不复制算法。

## 验证

用合成 XCI/NSP 覆盖共用入口的必填 title ID、非王国之泪 title ID 的选择、旧入口的默认行为和项目外工作目录复制。运行全量测试；核对真实马里奥本体与升级档的既有六层 IVFC、文件数和 SHA-256 证据。代码迁移不改变算法或热路径，不能从离线合并推导 FPS。

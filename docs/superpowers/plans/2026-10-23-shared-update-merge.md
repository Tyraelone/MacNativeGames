# 共用升级档 RomFS 合并工具实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已验证的 BKTR 合并器提升为要求显式 title ID 的共用离线工具，保留王国之泪旧入口。

**Architecture:** `game_tools/extract_update_romfs.py` 保存唯一合并实现，按包或脚本运行时分别导入共用 ExeFS/RomFS 工具；王国之泪原路径变为薄兼容层。共用 API 和命令要求 title ID，兼容层提供旧默认值。

**Tech Stack:** Python 3、unittest、现有固定 hactool。

**Spec:** `docs/superpowers/specs/2026-10-23-shared-update-merge-design.md`

## Global Constraints

- 游戏输入、密钥、合并产物、临时 NCA 和缓存均放在源码目录外。
- 不改变 BKTR、IVFC、哈希、私有密钥或外部输出的算法语义。
- 不改运行时、Metal、逐帧或逐绘制路径。

## Review Focus

- 共用命令缺少 title ID：参数解析拒绝，不回退到王国之泪。
- 共用 API 缺少或提供错误 title ID：在写输出前拒绝。
- 组合 XCI 包含多个游戏：按显式 title ID 选正确 Program。
- 旧构建命令不传 title ID：仍选王国之泪并与既有测试兼容。
- 项目外工作目录复制后：兼容入口能找到共用实现并正常显示帮助。

---

### Task 1: 固定共用与兼容接口

**Files:**
- Modify: `tests/test_updates.py`
- Modify: `tests/test_shared_game_tools.py`
- Create: `game_tools/extract_update_romfs.py`
- Modify: `games/totk/scripts/extract_update_romfs.py`

**Interfaces:**
- Consumes: `game_tools.extract_exefs`, `game_tools.extract_romfs`。
- Produces: `merge(base, update, keys_path, hactool, output, *, base_romfs=None, title_id)`；`main(default_title_id=None)`；旧 `merge` 和 `main` 保留王国之泪默认 ID。

- [x] **Step 1: Write the failing tests.** `tests/test_updates.py` 验证共用 `merge` 要求 title ID、错误 ID 不产生输出、非王国之泪组合 XCI 可按指定 ID 合并；`tests/test_shared_game_tools.py` 验证共用 CLI 缺少 `--title-id` 被拒绝、旧脚本从复制后的工作目录可启动。
- [x] **Step 2: Run the focused tests and confirm failure from the absent shared module.** `PYTHONDONTWRITEBYTECODE=1 /tmp/mng-generic-porting-venv/bin/python -m unittest discover -s tests -p 'test_updates.py' -q`。
- [x] **Step 3: Move the existing implementation into `game_tools/`, switch its imports to package/script-aware imports, require `title_id`, and replace the old file with a delegating compatibility entry.** Keep hactool arguments, checks and output format unchanged.
- [x] **Step 4: Run both focused test files, then all Python tests.** Use `SDKROOT=/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX26.5.sdk PYTHONDONTWRITEBYTECODE=1 /tmp/mng-generic-porting-venv/bin/python -m unittest discover -s tests -q`.
- [x] **Step 5: Update README and the input matrix with the shared command and evidence boundary; verify `git diff --check`, review the diff and commit.**

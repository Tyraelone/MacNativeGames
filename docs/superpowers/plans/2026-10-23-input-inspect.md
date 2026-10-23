# 游戏输入只读检查器实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在统一入口增加可复验的只读游戏输入检查，并对马里奥样本准确报告待适配状态。

**Architecture:** `build_game.py` 只转交命令；`inspect_game.py` 先读取 NCA 身份，再在项目外临时目录调用已有 ExeFS、NSO 和依赖工具，最后汇总 JSON。确切 ExeFS 哈希负责版本识别；静态导入只作为线索。

**Tech Stack:** Python 3、现有 `extract_exefs.py`/`prepare_modules.py`/`map_dependencies.py`、`unittest`。

**Spec:** `docs/superpowers/specs/2026-10-23-input-inspect-design.md`

## Global Constraints

- 输入与密钥只读；所有临时文件必须位于源码目录外并在退出时删除。
- 不根据文件名判断版本，不复制游戏数据到源码目录。
- 输出中的能力状态不得从静态导入推断为已实现或已运行。

## Review Focus

- 组合 XCI 多 Program 且未传 title ID：明确报错。
- 升级档 Program 使用基础 title ID：按 BKTR 与元数据核对，不误判为本体。
- 缺少密钥、票据或哈希损坏：非零退出且无成功 JSON。
- 包含 `subsdk0` 与不包含它的游戏：模块盘点都工作。
- 文件名伪装已支持版本：只有完整 ExeFS 哈希匹配才识别版本。

---

### Task 1: 输入身份与状态模型

**Files:** Create `inspect_game.py`; Test `tests/test_inspect_game.py`.

**Interfaces:** `select_program(path, keys, title_id=None)` 返回容器类型、基础 title ID 与基础/升级档身份；`match_profile(title_id, files)` 返回确切版本或 `None`。

- [x] 写失败测试：单 Program 基础包、BKTR 升级档、组合包歧义、伪装文件名与已知哈希。
- [x] 运行目标测试确认 RED。
- [x] 用现有容器函数实现选择与哈希匹配。
- [x] 运行目标测试确认 GREEN。

### Task 2: 临时验证与 JSON 报告

**Files:** Modify `inspect_game.py`; Test `tests/test_inspect_game.py`.

**Interfaces:** `inspect(path, keys, title_id=None)` 运行现有工具并返回 JSON 可序列化字典；CLI 输出该字典。

- [x] 写失败测试：三种状态、未评估能力、无源码产物和失败退出。
- [x] 运行目标测试确认 RED。
- [x] 在项目外 `TemporaryDirectory` 中调用提取、NSO、依赖工具；汇总并删除临时数据。
- [x] 运行目标测试确认 GREEN。

### Task 3: 统一入口与真实样本

**Files:** Modify `build_game.py`, `tests/test_build_game.py`, `docs/mario-wonder-input-probe.md`.

**Interfaces:** `build_game.py inspect GAME --keys PROD.KEYS [--title-id HEX]`。

- [x] 写失败测试：帮助和参数精确转交，不影响现有目标路由。
- [x] 运行目标测试确认 RED。
- [x] 实现转交并运行目标测试确认 GREEN。
- [x] 对马里奥本体和升级档运行真实只读检查；核对状态、模块和临时目录清理。
- [x] 运行 71 项以上完整测试、`git diff --check`，记录实际结果并提交。

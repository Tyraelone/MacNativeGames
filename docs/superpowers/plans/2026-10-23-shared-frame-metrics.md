# 共用 NVN 帧时间汇总实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给多款游戏提供同一套只读帧时间分布和样本覆盖率统计。

**Architecture:** `game_tools/frame_metrics.py` 按帧解析 NVN TSV 并暴露纯函数及 CLI；王国之泪场景脚本复用它，保留原报告字段。

**Tech Stack:** Python 3.14、unittest、现有 DM_NVN_TSV 格式。

**Spec:** `docs/superpowers/specs/2026-10-23-shared-frame-metrics.md`

## Global Constraints

- 不修改游戏运行时、计时采样、Metal 绘制或逐帧路径。
- 测试使用合成 TSV，测试文件与真实日志均在源码目录外。
- 真实性能结论须来自独立游戏槽与同场景 A/B 数据；本计划不声称获得该数据。

## Review Focus

- 缺失/无效帧会不会被悄悄排除，却仍标成完整样本。
- 同帧重复指标会不会混入拼接日志。
- 小样本 p95/p99 会不会低估最慢帧。
- GPU 回读缺样本时会不会把 CPU 帧时间当 GPU 数据。
- 现有 `mac_v143_smoke.py` 从项目外构建工作目录运行时能否找到共用工具。

---

### Task 1: 共用汇总器与旧调用兼容

**Files:**
- Create: `game_tools/frame_metrics.py`
- Create: `tests/test_frame_metrics.py`
- Modify: `games/totk/scripts/mac_v143_smoke.py`
- Modify: `docs/performance-followups.md`

**Interfaces:**
- Produces: `summarize_tsv(path: Path, first: int, last: int, budget_ms: float = 1000/60) -> dict`。
- Consumed by: `mac_v143_smoke.summarize(path, first, last)`，其 `scope` 文本继续由该脚本附加。

- [x] **Step 1: Write synthetic failing tests.** 检查最近秩 p50/p95/p99、超预算比例、缺帧/无效样本、GPU 覆盖和管线计数；重复指标拒绝；CLI 只输出 JSON；旧脚本入口保留字段。
- [x] **Step 2: Run focused tests and see failure from the absent module.** `PYTHONDONTWRITEBYTECODE=1 /tmp/mng-generic-porting-venv/bin/python -m unittest discover -s tests -p test_frame_metrics.py -q`。
- [x] **Step 3: Implement streaming TSV parse and statistics in `game_tools/frame_metrics.py`; delegate the old script's summary to it.** No game launch, file write or runtime edits.
- [x] **Step 4: Run focused and full Python tests, inspect a synthetic CLI report, and check `git diff --check`.**
- [x] **Step 5: Record limitations and command in performance docs, review the diff, then commit.**

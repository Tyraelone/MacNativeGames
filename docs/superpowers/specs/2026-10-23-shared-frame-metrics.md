# 共用 NVN 帧时间汇总设计

## 目的

把现有《王国之泪》场景脚本内的 TSV 帧时间汇总提取为游戏无关的离线工具。对同一帧窗口报告完整的有效 `@frame_ms` 分布、超预算比例、GPU 时间和新增管线数，并明确缺帧或无效样本。工具只读取项目外诊断日志，不进入游戏进程或绘制热路径。

## 接口

`game_tools.frame_metrics.summarize_tsv(path, first, last, budget_ms=1000/60)` 返回 JSON 可序列化字典。帧范围含两端；相同帧的重复指标拒绝，避免把拼接的多次运行当作一次样本。非有限、非正的帧时间不计入分位数，但计入无效样本；缺少帧时间的帧数独立报告。分位数用最近秩法（`ceil(q*n)-1`），避免少样本时低估尾部。`@gpu_ms`、`@pso_new` 只作为辅助指标，GPU 缺样本不能用 CPU 帧时间代替。

CLI 为 `python3 game_tools/frame_metrics.py TSV --first N --last N [--budget-ms M]`，只输出摘要，不写文件。《王国之泪》现有场景脚本调用同一实现，并保留原有字段 `first_frame`、`last_frame`、`measured_frames`、`fps_mean`、`frame_ms_p50/p95/p99`、`gpu_ms_p50`、`scope`，增加覆盖率和慢帧字段。

## 边界

这是数据汇总工具，不代表场景已固定或新游戏可运行。公平 A/B 测试仍须按 `docs/performance-followups.md` 使用同机、同场景、同模式、冷热缓存分开和独立游戏槽；不能将两组分位数直接相减后宣称因果。日志未采集时只能报告未测，不能把合成测试当作真实 FPS。

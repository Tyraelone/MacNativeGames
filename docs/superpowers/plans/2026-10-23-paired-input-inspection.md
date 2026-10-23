# 本体与升级档配对检查实施计划

Spec: `docs/superpowers/specs/2026-10-23-paired-input-inspection.md`

- [x] 先用合成报告测试配对身份、错误角色、不同 title 和升级档容器限制，确认新测试失败。
- [x] 给 `inspect_game.py` 增加只读 `inspect_pair` 和可选 `--update`，单输入 JSON 保持不变。
- [x] 用合成报告走 CLI 分派并验证失败时标准输出为空；现有单输入测试保留合成容器检查。
- [x] 用马里奥本体/升级档真实输入跑配对检查，报告写在项目外；确认状态仍为 `unported_title`。
- [x] 更新 README 和输入矩阵，跑全量回归、检查 diff 与工作区，再提交。

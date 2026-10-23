# 本体与升级档配对检查

## 目标

在大体积 BKTR 合并或打包前，对用户提供的本体和独立升级档执行同一套只读代码身份检查，并确认二者属于同一基础 title。单独输入的 `inspect` JSON 及退出码保持原样。

## 接口

`python3 build_game.py inspect BASE --update UPDATE --keys PROD.KEYS [--title-id HEX]`。`--title-id` 只为含多个 Program 的本体 XCI 选定基础 title；升级档必须是独立 NSP。两个输入依次调用现有 `inspect`，沿用容器、CNMT、ExeFS 和 NSO 的验证与项目外临时目录清理。检查本体为 `base`、升级档为 `update`、基础 title ID 相同；任一条件失败时退出非零，不输出成功 JSON。

成功报告将两份原始单输入报告完整放在 `base` 和 `update` 字段，另列 `pair_identity: pass`、title ID 与限定范围说明。CNMT 未评估时不把它写成通过；两份各自的 `checks` 保持可见。配对结果只证明输入结构和代码身份，不表示版本得到支持、RomFS 已合并、宿主可执行或性能达标。

## 性能和文件边界

该命令只在打包前运行；不改变游戏进程、GPU 路径、逐帧统计或着色器缓存。测试使用合成容器与项目外临时目录，真实马里奥输入只读取、报告写到项目外，密钥内容不记录。

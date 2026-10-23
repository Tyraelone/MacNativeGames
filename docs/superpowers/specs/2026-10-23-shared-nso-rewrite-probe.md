# 共用 NSO 改写探针

## 目标

把已验证 ExeFS 到现有 ARM64 指令改写器之间的调用做成游戏无关的离线入口。模块集合来自实际 ExeFS，不预设 `subsdk0`。探针只验证改写器能处理该版本的代码，不生成 App 或声称宿主已能执行。

## 接口

`python3 game_tools/rewrite_modules.py --exefs EXEFS --manifest extraction-manifest.json --output OUT`。输入和输出均位于源码目录外，输出路径须尚不存在。先将 ExeFS 中每个 NSO 的大小和 SHA-256 与验证过的提取清单逐一比对，再用项目现有改写器处理实际模块。输出目录含逐模块改写数据及 `rewrite-summary.json`；标准输出只给小型 JSON 摘要。全部模块成功才以原子目录改名公布结果，失败时删除本次临时输出。

为防止把旧游戏的定点补丁误认为通用机制，此入口固定使用 `DM_RULESET=native`、关闭私有门，并拒绝任何 `cuts`、`params` 或 `obs` 记录。已登记定点补丁继续由各游戏构建器处理。结果标注 `runtime: not_assessed`，仍需重定位、宿主服务、NVN、画面与性能测试。

## 性能边界

工具只在离线准备阶段运行，读取/写入项目外文件，不修改游戏运行时代码路径。该命令的耗时是改写耗时，不是游戏帧时间；真实性能须使用同场景 A/B 和完整帧分布复验。

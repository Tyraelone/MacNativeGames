# 通用构建入口第一阶段实施计划

Spec: `docs/superpowers/specs/2026-10-23-generic-build-entry-design.md`

## 文件职责

- `build_game.py`：只读目标目录、帮助信息与安全的子进程分派；不生成游戏文件。
- `tests/test_build_game.py`：无游戏数据的命令行行为与分派检查。
- `README.md`：说明统一入口的三种成熟度，保留原入口文档。

## 全局约束

- `AGENTS.md`：游戏 App、解包数据、缓存和临时测试产物留在源码目录外。
- 不改动已有三个构建器、运行时、着色器热路径或其命令行语义。
- 使用当前 Python 解释器执行固定仓库脚本；传参使用列表，不经 shell。
- 未知游戏或版本不得标记为支持。

## Task 1：固定目标目录与帮助

1. 在 `tests/test_build_game.py` 写测试，执行 `build_game.py list`，检查三个目标及状态；执行顶层 `--help`，检查所有目标和各自输入条件；未知目标必须非零退出。运行测试，确认因入口尚不存在而失败。
2. 新增 `build_game.py`：定义静态目标信息（名称、title ID、状态、脚本路径、条件），实现 `list`、顶层帮助与未知目标错误。运行该测试确认通过。
3. 验证：`PYTHONDONTWRITEBYTECODE=1 <venv-python> -m unittest discover -s tests -p test_build_game.py -v`。

## Task 2：精确分派及退出码

1. 扩展 `tests/test_build_game.py`：针对三个目标，对纯函数 `command_for(target, args)` 检查脚本绝对路径、当前 Python 解释器、参数顺序及特殊字符原样保留；用项目外临时脚本检查正常退出码原样返回、信号终止转为 `128 + 信号编号`；目标后的 `--help` 传给旧脚本。测试先失败，原因应是函数尚不存在或状态转换尚未实现。
2. 在 `build_game.py` 实现纯函数与分派。只允许目录里的固定脚本，不运行用户指定路径。不要解析或改写旧脚本参数。
3. 验证目标测试及现有全集。全量命令：`SDKROOT=<Xcode 26.5 SDK> PYTHONDONTWRITEBYTECODE=1 <venv-python> -m unittest discover -s tests -v`。

## Task 3：文档和最终核验

1. 在 `README.md` 中文、英文入口附近增加统一命令示例和能力边界。原三个脚本继续可用，卡比/恶魔城仍需项目外已验证输入。
2. 检查 `git diff --check`、顶层 `--help`、`list`、三个目标的 `--help`，以及全量 55 项基线加新增测试。
3. 复查本阶段只改源码、测试和文档；`git status --short` 中不能有 App、解包数据、缓存或编译产物。

## 后续阶段

这份计划不实现版本配置注册、只读兼容诊断或运行时语义收敛。它们依赖已有入口先统一并经过回归，随后分别制定计划；不得把本阶段完成写成“任意游戏可直接构建”。

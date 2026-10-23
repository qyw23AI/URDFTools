# URDFTools

> **当前开发方式**：在本对话按小时继续开发、运行真实验收并保存 Git 证据。历史 Python/systemd 开发调度器不再使用。最新阶段状态以 [PROGRESS.md](PROGRESS.md) 为准；正式安装包和完整评估功能仍在开发。

面向强化学习机器人研发的本地桌面工作台、Python 工具包与 agent 工具。已有 URDF 查看、CAD→URDF 转换、参数化建模、静态/无训练物理检查和外部训练结果导入的阶段性能力；评估结论仍需明确实验来源、协议和不确定性。本项目不开发或运行 RL 训练器。阶段 gate 通过不等于全部应用交付。

## 本地开发版启动（非正式安装包）

`apps/web/index.html` 是 Vite 源码入口，不能通过浏览器的 `file://` 直接运行。
若只想查看界面，在项目根目录启动本机预览：

```bash
cd ~/URDFTools
PATH="$PWD/.tools/node/bin:$PATH" .tools/node/bin/node .tools/npm/bin/npm-cli.js run build
PATH="$PWD/.tools/node/bin:$PATH" .tools/node/bin/node .tools/npm/bin/npm-cli.js run preview -- --port 5173
```

随后打开 `http://127.0.0.1:5173/`。浏览器预览会明确标出需要桌面端的操作；URDF 文件夹导入、CAD 转换与参数化建模由 Electron 的本地接口提供。

在本机 GNOME 图形会话中执行：

```bash
cd ~/URDFTools
./scripts/launch-dev-desktop.sh
```

在「查看」页面拖入 URDF 所在文件夹或 ZIP，选择模型后可旋转/缩放，浏览 Link/Joint 树，切换 Visual/Collision，查看显式质心/惯量、近似包围盒，并用关节滑块调整姿态或导出 PNG。此脚本从源代码本地构建，不关闭 Electron 沙箱，也不会打开外部训练器。若未配置 S01 的独立工具链，请先阅读 `docs/TOOLCHAIN.md`；正式 AppImage/GNOME 收藏夹安装仍安排在 Q01/Q02。

- [需求基线](docs/REQUIREMENTS.md)
- [技术架构](docs/ARCHITECTURE.md)
- [评估/对照实验方法](docs/EVALUATION.md)
- [开源方案检索](docs/RESEARCH.md)
- [50 个阶段与模型分工](docs/TASKS.md)
- [自动调度设计](docs/SCHEDULER_DESIGN.md)
- [运行与交接](docs/OPERATIONS.md)
- [当前进度](PROGRESS.md)
- [外部结果包导入指南（B08 开发中）](docs/RESULTS_IMPORT_GUIDE.md)
- [开发环境与离线输入](docs/TOOLCHAIN.md)
- [S01 实际验收](docs/acceptance/S01.md)
- [S03 导入验收](docs/acceptance/S03.md)
- [S04 三维查看验收](docs/acceptance/S04.md)
- [S05 查看器分析工具验收](docs/acceptance/S05.md)
- [S06 Go2/G1 真实模型端到端验收](docs/acceptance/S06.md)
- [查看模块操作指南](docs/VIEWER_GUIDE.md)
- [C00 STEP 内核与转换原型技术验收](docs/acceptance/C00.md)
- [C00 STEP/OpenCascade 内核预检历史记录](docs/CAD_KERNEL_PREFLIGHT.md)
- [C01 CAD 质量、质心、惯量与坐标变换验收](docs/acceptance/C01.md)

当前按 `AGENTS.md` 和 `PROGRESS.md` 直接开发、逐阶段验收。旧调度器文件仅保留历史记录。

## 2026-10-22 用户范围修订与恢复

产品采用外部训练结果库与证据分析架构，详见 docs/RESULTS_DATABASE.md、docs/TASKS.md；不实现 RL 训练器。普通/复杂/关键分别 Sol Low/Medium/High，Astra 当前不启用。S01 上次真实 gate 通过，但 Chromium 许可证触发大文件检查而未提交；已逐字节核验官方运行时文件并精确放行。本次保留原始成果，交调度器真实重验与提交，不能将该运维修订当 S01 已完成。小时 timer 和防并发锁保留。

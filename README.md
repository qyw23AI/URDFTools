# URDFTools

> **2026-10-22 开发方式更新**：网页版 ChatGPT + WebCodex 负责主要构建；任务调度器仅用于阶段性检查和改进。S03–S06 查看模块通过各自声明 gate 与真实 Electron 验收；C00 STEP 检查与 C01 CAD 质量/惯量后端原型均通过 3/3 技术 gate，阶段完成状态仍待调度器复核。最终 GNOME 收藏夹应用、CAD→URDF 生成、材料分配 UI、Agent 和训练结果评估仍未全部交付。

面向强化学习机器人研发的本地桌面工作台、Python 工具包与 agent 工具。目标功能为 URDF 查看、CAD→URDF 转换、参数化 CAD/机器人建模，以及有证据的训练适用性评估与机械反馈。**S01 工具链、S02 数据契约、S03–S06 查看模块（含真实 Go2/G1 模型）、C00 STEP 检查与 C01 CAD 质量/惯量后端原型均已有实际技术验收；完整 CAD→URDF 生成、关节推断、材料分配 UI、Agent、真实机器人物理合理性/训练结果评估和正式发行包仍未全部实现。阶段技术 gate 通过不等于全部应用交付。**

## 本地开发版启动（非正式安装包）

在本机 GNOME 图形会话中执行：

```bash
cd ~/URDFTools
bash scripts/launch-dev-desktop.sh
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

按用户 2026-10-22 最新决定，主要功能由当前网页版 ChatGPT + WebCodex 主动构建并逐阶段验收；任务调度器仅用于后续成果复核与改进，不是开发入口或前置条件。

默认模型配置已经下调：50 个阶段中 Sol Low 20、Sol Medium 28、Sol High 2、Astra 0。高难模型仍可作为明示、受预算约束的复核档，但不会自动升级。

## 2026-10-22 用户范围修订与恢复

产品采用外部训练结果库与证据分析架构，详见 docs/RESULTS_DATABASE.md、docs/TASKS.md；不实现 RL 训练器。普通/复杂/关键分别 Sol Low/Medium/High，Astra 当前不启用。S01 上次真实 gate 通过，但 Chromium 许可证触发大文件检查而未提交；已逐字节核验官方运行时文件并精确放行。本次保留原始成果，交调度器真实重验与提交，不能将该运维修订当 S01 已完成。小时 timer 和防并发锁保留。

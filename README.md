# URDFTools

面向强化学习机器人研发的本地桌面工作台、Python 工具包与 agent 工具。目标功能为 URDF 查看、CAD→URDF 转换、参数化 CAD/机器人建模，以及有证据的训练适用性评估与机械反馈。**当前有开发工具链、CLI/服务及前端空壳；S01 工具链和真实无头桌面门禁已通过，正式阶段状态由调度器决定。机器人功能尚在开发。**

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

开发由 `scheduler.py` 与 `urdftools-dev.timer` 驱动，策略以 `scheduler.json` 和实际部署为准，真实开发状态可用 `python3 scheduler.py status` 检查。额度、认证、硬件条件不足时保留阶段等待再试。

默认模型配置已经下调：50 个阶段中 Sol Low 20、Sol Medium 28、Sol High 2、Astra 0。高难模型仍可作为明示、受预算约束的复核档，但不会自动升级。

## 2026-10-22 用户范围修订与恢复

产品采用外部训练结果库与证据分析架构，详见 docs/RESULTS_DATABASE.md、docs/TASKS.md；不实现 RL 训练器。普通/复杂/关键分别 Sol Low/Medium/High，Astra 当前不启用。S01 上次真实 gate 通过，但 Chromium 许可证触发大文件检查而未提交；已逐字节核验官方运行时文件并精确放行。本次保留原始成果，交调度器真实重验与提交，不能将该运维修订当 S01 已完成。小时 timer 和防并发锁保留。

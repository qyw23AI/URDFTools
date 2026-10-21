# URDFTools

面向强化学习机器人研发的本地桌面工作台、Python 工具包与 agent 工具。目标功能为 URDF 查看、CAD→URDF 转换、参数化 CAD/机器人建模，以及有证据的训练适用性评估与机械反馈。**当前只有架构和阶段计划，产品功能尚在开发。**

- [需求基线](docs/REQUIREMENTS.md)
- [技术架构](docs/ARCHITECTURE.md)
- [评估/对照实验方法](docs/EVALUATION.md)
- [开源方案检索](docs/RESEARCH.md)
- [50 个阶段与模型分工](docs/TASKS.md)
- [自动调度设计](docs/SCHEDULER_DESIGN.md)
- [运行与交接](docs/OPERATIONS.md)
- [当前进度](PROGRESS.md)

开发由已有 `scheduler.py` 与 `urdftools-dev.timer` 驱动，默认每 6 小时尝试下一任务。现有 S00 加固完成前，CLI 仍按初始实现每轮执行一个顺序任务；`scheduler.json` 中的新策略字段供 S00 实现，不应误解为已经生效。真实开发状态可用 `python3 scheduler.py status` 检查。额度、认证、硬件条件不足时保留阶段等待再试。

默认模型配置已经下调：50 个阶段中 Sol Medium 20、Sol High 28、Astra High 2、Astra xHigh 0。高难模型仍可作为明示、受预算约束的复核档，但不会自动升级。

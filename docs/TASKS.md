# 阶段计划 v2

2026-10-22 按用户明确要求修订，保留 50 个阶段 ID 和既有验收入口。训练实现改为外部结果数据库及分析。详细交付和数值验收见 tasks/<id>.md。

| ID | 阶段 | 等级 | 依赖 |
|---|---|---|---|
| S00 | 加固自动开发调度器 | complex | — |
| S01 | 项目与可复现工具链 | ordinary | S00 |
| S02 | 领域模型与接口契约 | complex | S01 |
| S03 | URDF 文件夹与 ZIP 导入 | complex | S02 |
| S04 | 三维查看基础 | complex | S03 |
| S05 | 查看器分析工具 | complex | S04 |
| S06 | 查看模块整体验收 | ordinary | S05 |
| C00 | STEP 内核与转换原型 | complex | S03 |
| C01 | 质量惯量与坐标变换 | complex | C00 |
| C02 | 关节分组与转换向导 | complex | C01, S04 |
| C03 | URDF/ROS 包导出与交叉校验 | complex | C02 |
| C04 | 其他 CAD 和 SolidWorks 互通 | ordinary | C03 |
| M00 | 参数化 CAD 操作核心 | complex | C01 |
| M01 | 交互式机器人建模界面 | complex | M00, S05 |
| M02 | FreeCAD 往返与版本差异 | complex | M01, C04 |
| A00 | 受约束 Agent 工具层 | complex | S02, M00 |
| A01 | Agent 辅助建模 | complex | A00, M01 |
| A02 | CLI 与 MCP 工具接口 | ordinary | A00, C03 |
| E00 | 评估方法审查与金标准故障集 | critical | S02 |
| E01 | 静态语义与物理规则 | ordinary | E00, C01 |
| E02 | 动力学一致性检查 | complex | E01 |
| E03 | URDF 到 MuJoCo 的可靠编译 | complex | E02, C03 |
| E04 | 无训练动态探测 | complex | E03 |
| R00 | 参照模型注册表 | ordinary | S01, E00 |
| R01 | A1 与 Go2 参照模型 | ordinary | R00, E03 |
| R02 | G1 与 H1 参照模型 | ordinary | R00, E03 |
| K00 | 可扩展技能机制和动力学基础 | ordinary | E00, A02 |
| K01 | 四足评估技能 | complex | K00, R01, E04 |
| K02 | 人形评估技能 | complex | K00, R02, E04 |
| B00 | 可恢复的结果导入与分析作业 | complex | S02, S01 |
| B01 | 标准训练结果数据库与导入 | complex | B00 |
| B02 | 四足结果协议与参照入库 | complex | B01, R01 |
| B03 | 人形结果协议与参照入库 | complex | B01, R02 |
| B04 | 地形与扰动结果协议 | ordinary | B02, B03 |
| B05 | 统计与公平对照引擎 | complex | B04 |
| B06 | 外部日志适配与结果交换 | ordinary | B01 |
| B07 | 视频时序与交互对照 | ordinary | B05, S05 |
| B08 | 两类机器人结果导入端到端验收 | ordinary | B02, B03, B07 |
| D00 | 受证据约束的诊断引擎 | critical | E04, K01, K02, B05 |
| D01 | 消融建议与外部复验闭环 | complex | D00, B08 |
| D02 | 机械组报告与 CAD 映射 | ordinary | D01, M02, B07 |
| D03 | Agent 调用技能解释对照 | complex | D00, A01, D02 |
| Q00 | 跨模块回归与用户流程 | complex | S06, C04, M02, D03 |
| Q01 | 离线发行包与第三方许可 | complex | Q00 |
| Q02 | Ubuntu 收藏夹安装 | ordinary | Q01 |
| Q03 | 软件发行验收审查 | ordinary | Q02, B08, B06 |
| X00 | Go2 标准结果库工作流 | ordinary | Q03, B05 |
| X01 | G1 标准结果库工作流 | ordinary | Q03, B05 |
| X02 | A1/H1 扩展与变体分析 | ordinary | X00, X01, D01 |
| Q04 | 最终全量交付核查 | ordinary | X02, Q03 |

普通 Sol Low；复杂 Sol Medium；关键 Sol High。Astra High 仅保留显式选择入口，当前队列无该档。无自动升档、无付费 API。

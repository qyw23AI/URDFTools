# 阶段任务与模型分工

由简单模块逐步进入评估与参考训练；具体依赖、验收命令和阶段说明均在 `scheduler.json` 与 `tasks/<id>.md`。S00 完成后调度器应按依赖选择可执行任务。

默认模型：ordinary=Sol Medium，complex=Sol High，critical=Astra High；本计划不默认使用 Astra xHigh。如必要，只能在有证据的架构复核任务中另行配置。

| 阶段 | 任务 | 模型 | 依赖 | 核心验收 |
|---|---|---|---|---|
| S00 | 加固自动开发调度器 | Sol High | — | 真实 CLI 小任务与故障注入测试：零测试、partial 退出0、429、额度未知、进程中断、重复运行、Git 恢复。不可缩减后续计划。 |
| S01 | 项目与可复现工具链 | Sol Medium | S00 | 全新目录能安装、启动 CLI/服务/前端空壳 |
| S02 | 领域模型与接口契约 | Sol High | S01 | 解析并保存自制双连杆和四足树，roundtrip 数值语义 |
| S03 | URDF 文件夹与 ZIP 导入 | Sol High | S02 | 真实夹具覆盖 package://、相对路径、缺失 mesh、ZIP 路径越界和多模型选择 |
| S04 | 三维查看基础 | Sol High | S03 | 离线打开示例文件夹，手动或浏览器 E2E 证明关节真实联动、mesh 显示、缺失资源提示。 |
| S05 | 查看器分析工具 | Sol High | S04 | 真实模型测试量测和关节数值 |
| S06 | 查看模块整体验收 | Sol Medium | S05 | 桌面端从拖入到检查关节/碰撞的演示证据齐全，资产许可被记录 |
| C00 | STEP 内核与转换原型 | Sol High | S03 | 自制两零件 STEP 与单零件 STEP 实测导入 |
| C01 | 质量惯量与坐标变换 | Sol High | C00 | 解析长方体、偏置双球、旋转非对角惯量的数值与独立公式吻合 |
| C02 | 关节分组与转换向导 | Sol High | C01, S04 | 重做同一配置得到等价 URDF |
| C03 | URDF/ROS 包导出与交叉校验 | Sol High | C02 | 真实 STEP→包→重新导入→FK/质量一致 |
| C04 | 其他 CAD 和 SolidWorks 互通 | Sol Medium | C03 | 各格式至少一个真实夹具 |
| M00 | 参数化 CAD 操作核心 | Sol High | C01 | 生成含孔支架及两连杆零件，参数修改触发几何和惯量重算 |
| M01 | 交互式机器人建模界面 | Sol High | M00, S05 | 用户从空项目建双连杆并导出可加载 URDF |
| M02 | FreeCAD 往返与版本差异 | Sol High | M01, C04 | 同零件可重关联 |
| A00 | 受约束 Agent 工具层 | Sol High | S02, M00 | 无效/越权调用拒绝 |
| A01 | Agent 辅助建模 | Sol High | A00, M01 | 用真实已有登录完成双连杆修改建议、人工接受/拒绝，接受后 URDF 验证通过并可撤销。 |
| A02 | CLI 与 MCP 工具接口 | Sol Medium | A00, C03 | CLI JSON 与 MCP 返回同 schema/错误语义 |
| E00 | 评估方法审查与金标准故障集 | Astra High | S02 | 故障集含误单位、错误惯量/轴及合法固定 frame/中空体 |
| E01 | 静态语义与物理规则 | Sol Medium | E00, C01 | 所有金标准夹具给出正确对象/数值/来源，合法反例不误报 |
| E02 | 动力学一致性检查 | Sol High | E01 | 双连杆解析力学与不同姿态一致，错误坐标系夹具被发现，固定 frame 无假阳性。 |
| E03 | URDF 到 MuJoCo 的可靠编译 | Sol High | E02, C03 | 四足/人形模型编译并生成 hash/映射，质量与关节 DOF 可对账 |
| E04 | 无训练动态探测 | Sol High | E03 | 真实 MuJoCo CPU 探测输出可复算日志/短视频 |
| R00 | 参照模型注册表 | Sol Medium | S01, E00 | 同名不同版本不覆盖 |
| R01 | A1 与 Go2 参照模型 | Sol Medium | R00, E03 | 两型号可查看和编译 |
| R02 | G1 与 H1 参照模型 | Sol Medium | R00, E03 | 两型号可查看和编译，动作维度及来源对账 |
| K00 | 可扩展技能机制和动力学基础 | Sol Medium | E00, A02 | 用户添加本地新 skill 能被发现且回归 |
| K01 | 四足评估技能 | Sol High | K00, R01, E04 | 对 A1/Go2 与变异夹具检测预期问题 |
| K02 | 人形评估技能 | Sol High | K00, R02, E04 | G1/H1 及变异夹具通过/失败符合标注，静态支撑不能替代动态步态判断。 |
| B00 | 可恢复实验作业系统 | Sol High | E03, S01 | 杀死 worker 后可重启同配置，改 robot hash 不可误续 |
| B01 | CPU PPO 训练闭环 | Sol High | B00 | 小型四足真实训练、checkpoint 续训、评价与日志 |
| B02 | 四足统一运动任务 | Sol High | B01, R01 | Go2 的每类环境 reset/step 与评估可跑，地形和命令种子可复现。 |
| B03 | 人形统一运动任务 | Sol High | B01, R02 | G1 真实环境 CPU reset/step、短训练/回放可复现 |
| B04 | 粗糙地形与鲁棒性条件 | Sol Medium | B02, B03 | 固定 seed 地形一致，训练与测试 seed 不泄漏，扰动幅值和物理条件记入 run。 |
| B05 | 统计与公平对照引擎 | Sol High | B04 | 伪造数据的预期区间、单 seed/不同任务拒排和训练失败纳入分布均有测试。 |
| B06 | GPU 加速适配接口 | Sol Medium | B00, B02 | CPU 上跑完 adapter contract 和缺 GPU 状态 |
| B07 | 实验媒体与对照视图 | Sol Medium | B05, S05 | 真实短实验视频与指标时间可定位 |
| B08 | 两类机器人端到端真实烟测 | Sol Medium | B02, B03, B07 | 两个 run 都有真实 checkpoint/日志/视频/配置 hash，报告明确只属于单 seed smoke。 |
| D00 | 受证据约束的诊断引擎 | Astra High | E04, K01, K02, B05 | 训练差或数据缺失时不武断归因 URDF |
| D01 | 消融与敏感度实验 | Sol High | D00, B08 | 改变腿长同步重算质量/惯量与 joint frame |
| D02 | 机械组报告与 CAD 映射 | Sol Medium | D01, M02, B07 | 夹具中故障能定位 CAD 零件 |
| D03 | Agent 调用技能解释对照 | Sol High | D00, A01, D02 | 真实登录生成带 evidence id 的建议 |
| Q00 | 跨模块回归与用户流程 | Sol High | S06, C04, M02, D03 | 端到端桌面流程全部实际执行 |
| Q01 | 离线发行包与第三方许可 | Sol High | Q00 | 干净用户环境开 GUI 并读自带示例 |
| Q02 | Ubuntu 收藏夹安装 | Sol Medium | Q01 | 桌面搜索可启动 |
| Q03 | 软件发行验收审查 | Sol Medium | Q02, B08, B06 | 所有必需 UI/CLI/CAD/agent/CPU 训练通路实际过关 |
| X00 | Go2 多种子参考实验 | Sol Medium | Q03, B05 | 各 seed 的完整 manifest/训练曲线/失败/视频可核验 |
| X01 | G1 多种子参考实验 | Sol Medium | Q03, B05 | 真实 checkpoint/独立种子/全量失败/统计与视频归档 |
| X02 | A1/H1 扩展与变体比较 | Sol Medium | X00, X01, D01 | 真实 pilot 与报告、原始数据、变体 CAD/URDF 对应 |
| Q04 | 最终全量交付核查 | Sol Medium | X02, Q03 | 所有必需阶段有通过证据、安装包可启动、收藏夹可见、全量实验有真实来源 |

共 50 个必需阶段；其中 Sol Medium 20 个、Sol High 28 个、Astra High 2 个、Astra xHigh 默认 0 个。

执行顺序首先 S00，随后基础→查看→转换→建模→agent→评估→训练→报告→打包→真实多种子参考库。依赖允许无 GPU 时继续其它阶段。用户自己的 URDF 尚未提供，最终软件应支持导入后同协议评估；未实际评估用户模型不可声称完成该项实证。

## 需求覆盖与完成门槛

| 需求 | 阶段 | 实际完成门槛 |
|---|---|---|
| R01–R02 查看 | S03–S06 | 离线拖入文件夹、联动、视觉/碰撞/测量及桌面流程过关 |
| R03 转换 | C00–C04 | STEP 实物夹具转换、质量惯量对账、自包含包 roundtrip、CAD 桥说明 |
| R04–R05 建模/agent | M00–M02、A00–A02 | 建模及撤销、agent 预览与人工应用、CLI/MCP 与权限校验 |
| R06 训练适用性 | E00–E04、D00–D03 | 静态/动态/训练证据和受限归因报告通过反例集 |
| R07–R08 参照与 skills | R00–R02、K00–K02 | A1/Go2/G1/H1 可追溯资产，四足/人形规则可扩展 |
| R09–R10 对照/机械反馈 | B00–B08、X00–X02、D00–D03 | 真训练、多种子、指标/视频/差距解释及 CAD 部件定位 |
| R11–R12 自动模型与额度 | S00、全部阶段 | 真实 model/effort 记录、额度停止、6 小时恢复、Git 验收日志 |
| R13 完整应用 | Q00–Q04 | AppImage/便携包、GNOME 收藏夹、所有必需阶段真实通过 |

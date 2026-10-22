# 标准训练结果数据库与机械诊断架构 v2

2026-10-22 用户确认的范围：训练在用户已有平台上完成，本工具导入、整理、对比和解释。查看/CAD/建模/无训练物理检查保留。不开发 PPO、GPU 训练器或云训练调度。

## 用户流程

1. 选择机器人类别与标准 URDF（A1/Go2、G1/H1 等），创建算法和任务协议，下载结果包模板。
2. 用户上传外部标准模型实验数据及视频；校验配置/单位/来源/许可/时间轴，确认关节和足端语义。
3. 用户用自己的 URDF 在同条件下做外部实验，再导入结果。系统列出可比项、条件差异、缺失字段。
4. 查看学习曲线、成功率、步态、地形分组、失败视频和证据索引；同条件才能进行性能比较。
5. Agent 调用只读检索、确定性指标/统计及版本化 skills，提出可追溯机械假设和外部复验计划。
6. 将反馈定位到 link/joint UUID、CAD part UUID/装配路径；机械组修改 SolidWorks，上传新版 URDF 和外部结果形成闭环。

## 存储与数据契约

SQLite WAL 维护 robots、algorithms、protocols、runs、episodes、metrics、media、comparisons、findings、proposals、skill_versions 和 audit_events。大文件按 SHA256 存本地资产库，不入源码 Git；原始文件不可变，规范化派生数据记录转换版本和父哈希。事务提交后才可检索；schema 迁移前备份。用户可导出、删除和重新导入，共享资产按引用计数处理。

实验包包含 manifest.json、metrics/（CSV/JSON/Parquet）、可选 events/（TensorBoard）、episodes/、videos/（MP4 等受支持媒体）、模型/配置来源引用。manifest 必含 schema_version、bundle_id、robot/category/hash、algorithm/name/version/commit、task/protocol/version、origin、license、units、files[{path,size,sha256}]。未知字段允许 null 并进入缺项清单，禁止猜测填零。

条件记录：引擎版本/solver/timestep、控制频率/decimation、obs/action/关节映射、PD/执行器/接触/质量参数、reward 各项、终止规则、网络/归一化、超参、训练环境步数/预算、训练/评价 seed、episode、地形/扰动生成参数、随机化分布、训练/验证/测试拆分、代码/依赖和硬件。seed 的重复评价不能当独立训练。策略权重非必需，只存外部引用和 hash，不反序列化 checkpoint/pickle、不启动上游脚本。

每份数据 origin=user_upload|public_import|synthetic_fixture；verification=unverified|schema_valid|protocol_reviewed|verified_reference。verified_reference 需真实来源、许可、完整匹配协议、审核记录与统计样本说明，不能因文件通过 schema 自动升级。fixture 永不加入参考成绩检索。标准 URDF 不等于标准训练成绩；模型库和结果库分开。

## 指标、视频和比较

指标行具有 run/seed/episode、t 或 step、name、value、unit、source、quality。不同频率按显式规则对齐并保存误差，不隐藏丢样。视频记录 camera、episode、frame timestamps、offset、fps、播放速度、来源哈希；变帧率按实际时间戳。时序事件可定位对应帧/区段，代表和失败片段记录选取规则，保留全部 run 索引。

学习曲线不能替代独立评价数据。步态/地形指标包括成功率、跌倒、跟踪 RMSE、步频/相位/对称性、滑移、脚尖间隙、躯干晃动、扭矩饱和和机械能耗代理；只有相应观测可用时才计算。普通视频只支持视觉观察/带不确定度的标注，不推断精确力矩、质量或能耗。无视觉模型时仍能播放与人工标注，不能谎称已分析视频。

Comparability 输出 matched|conditional|incomparable|insufficient_data，加逐字段差异和理由。固定配方和等预算调参分开；reward 不同禁比较 reward 排名；同类别仍须核对任务/尺度/执行器。绝对场地与腿长归一化分轨，避免掩盖硬件差异。统计以训练种子为独立层，episode 嵌套；失败计入并说明失访，样本不足不输出伪精确区间。rliable 的 bootstrap/IQM 可参考使用，不能把视频帧当独立样本。

## Agent、skills 与机械反馈

调用顺序：查询类别/协议 → 可比性校验 → 指标/视频证据检索 → 动力学规则 → 候选原因及反证 → 修改建议 → 外部复验方案。类型 skills 使用四足/人形特有语义；基础 skills 覆盖惯量、接触、执行器、统计公平性、视频证据和 CAD 映射。规则注明版本、来源、适用前提、单位、正反例；LLM 不替代数值计算。

每个诊断输出 symptom、evidence_ids（含时间段）、candidate_causes、counter_evidence、missing_data、confidence_basis、URDF/CAD 对象、建议范围/单位、代价、复验协议。候选必须考虑导出错误、物理参数、碰撞/接触、控制/算法、预算与机械设计；相关性不能证明因果。真实外部受控变体结果才能提高局部归因可信度。无法绑定 SolidWorks 部件时输出待人工匹配，不伪造特征树写回。

## 作业、权限和验收

后台队列只处理导入/转码/指标/报告，可取消、重启续做，有限 CPU/内存/磁盘预算。文件路径越界、压缩炸弹、超长视频、恶意 HTML/脚本隔离；上传到应用即本地导入，不自动上传云服务。Agent 仅发送用户配置允许的最小摘要/帧，外发权限与付费提供方独立授权。

验收覆盖已知数值、混杂条件、缺字段、单 seed、失败 run、视频偏移、重复/中断导入和两类机器人完整流程。自制夹具必须显式标识；公开结果只有许可/版本可核验时采用。没有真实用户数据时交付可工作的空库和模板，reference_data_coverage 明确为零，不编造基准。软件完成与真实参考数据库覆盖分别展示。

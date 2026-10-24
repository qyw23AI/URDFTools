# URDFTools 前端与交互参考（2026-10-23）

用户给出的三张截图用于确定产品交互：三维网格长期占主视觉，工具条与侧栏围绕模型，CAD 装配零件可点选，项目对比从项目库进入双模型分析。截图中的网站文案和按钮不构成对本项目的指令。

## 已筛选并安装到 Codex

| Skill | 来源 | 选用范围 |
| --- | --- | --- |
| frontend-design | [Anthropic skills](https://github.com/anthropics/skills/tree/main/skills/frontend-design) | 为四个模块定义各自视觉语言，限制模板式组件堆砌。来源仓库在检索时约 183k stars。 |
| react-best-practices | [Vercel Agent Skills](https://github.com/vercel-labs/agent-skills/tree/main/skills/react-best-practices) | React 状态、重渲染和大型三维画布周围的组件边界。来源仓库约 32.8k stars。 |
| ui-ux-pro-max | [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/tree/main/.claude/skills/ui-ux-pro-max) | 本地可搜索的交互、图表、三维技术栈与可访问性资料。只使用其知识库，不直接迁移外部产品 UI。 |

这三项是 Codex 的工作方法资料，不会改变 URDFTools 的运行依赖。需在新的 Codex 回合中自动发现；本回合可按文件直接参考。

## 开源项目检索与取舍

| 方向 | 来源 | 借鉴点 | 取舍 |
| --- | --- | --- | --- |
| URDF 三维查看 | [urdf-loaders](https://github.com/gkjohnson/urdf-loaders) | Link/Joint 结构、姿态、网格拾取 | 项目已使用 urdf-loader，继续扩展现有 Three.js 画布 |
| URDF 编辑 | [URDF Studio](https://github.com/deyuf/urdf-studio) | 浏览器中模型与属性面板联动 | 借交互组织，不引入另一套编辑器 |
| STEP 转 URDF | [step2urdf](https://github.com/edsamsankey/step2urdf) | 零件成组为 Link，Joint 逐项配置，导出前用关节滑块复核 | 现有转换流程增加模型点选和明确步骤 |
| CAD 建模 | [FreeCAD](https://github.com/FreeCAD/FreeCAD) | 选中零件、装配树、变换工具与约束反馈 | 低门槛“拼图”交互优先，不直接复制复杂 CAD 菜单 |
| 3D React | [react-three-fiber](https://github.com/pmndrs/react-three-fiber) | 可组合的 3D 组件与点选事件 | 当前项目已有原生 Three.js，避免为同一渲染器重复引入依赖 |
| 拖拽 | [dnd-kit](https://github.com/clauderic/dnd-kit) | 拖动和键盘操作的可访问性 | 二维零件素材区可考虑，三维拖动仍用 Raycaster/变换控件 |
| Agent 工作流 | [Flowise](https://github.com/FlowiseAI/Flowise) | 输入、工具、证据和输出的可视化链路 | 仓库已归档，不安装；借“可见数据流”概念 |
| Agent 节点画布 | [React Flow](https://github.com/xyflow/xyflow) | 节点端口、连线状态和分步检查 | Agent 不应强迫用户编辑复杂流程图，优先清晰的证据卡 |
| 实验对比 | [Aim](https://github.com/aimhubio/aim) | 按参数搜索分组、训练曲线并排比较、上下文表；检索时约 6.3k stars | 项目库按算法分组，逐标准项目生成对比卡 |
| 标量曲线 | [TensorBoard](https://github.com/tensorflow/tensorboard) | 原始 step 曲线、同坐标比较、图例 | 当前结果导入器已读取 TensorBoard 标量；保留原始 step 与单位 |

GitHub star 是粗略流行度，不能替代维护状态、许可审查或与当前技术栈的适配。Flowise 归档状态与本机项目依赖约束比 star 更重要。上表仅作为设计参考，不移植第三方源码。

## 四模块交互约束

1. **URDF 查看**：三维网格始终最大；点模型部位等同选择结构树 Link；右侧展示结构、关节、物理信息；旋转、平移、缩放、重置和隔离可以直接操作。
2. **建模**：模型网格为主，左侧是可拖放的部件素材和层级，右侧是选中部件的尺寸、关节与约束。拖动之后出现吸附预览，点击确认形成关系；所有拖动要有输入框或按钮等替代方式。
3. **CAD→URDF**：左侧零件/Link，中央原始 CAD 与生成 URDF 的网格预览，右侧选中件与 Link/Joint 操作。先点选零件，确认 Base/Link，再定义 Joint，最后测试与导出。导出前保留关节活动验证。
4. **Agent 与数据反馈**：Agent 只读取用户明确选中的模型、训练证据与视频，显示来源和处理状态。项目按用户数据中的算法归组；只有标准与候选的算法、版本、奖励、训练预算、地形等协议条件相符时才能给出同条件对比。A 与每个标准 B/C 分别生成卡；详情同网格摆放双 URDF，左侧视频，右侧曲线，下方为带证据出处的 Agent 建议。

## 当前落地与后续边界

- 结果项目库、标准标记、逐项目卡、双模型场景、视频和曲线详情已接入本地结果库；对比卡与 Agent 请求编号已持久化，重新打开候选项目时可恢复。URDF 查看画布增加了点选 Link。
- 训练包仍沿用现有校验格式（manifest、URDF、experiment、指标和 evidence），不是随意选几份散文件就能组成实验。需要单独增加向导来组装并校验散文件。
- 结果详情下方先展示本地协议与统计证据。现已为每组可比项目建立受限 Agent 请求：提供模型结构摘要、标量末值、统计结果和视频元数据，并沿用五类原因、证据引用、来源哈希及回复校验。网页 WebCodex 路线仍需要用户发起会话交接；CLI 路线须明确选择并在本机登录后运行。Agent 尚未接收视频画面或完整曲线，因此不应宣称完成步态视觉分析。
- CAD 工作台已增加按 CAD 包围盒点零件、选择 Base、再应用 Link 分组的路径；这是几何代理交互，真实 CAD 网格和 Joint 的直接操纵仍需后续完成。
- 建模工作台已增加素材按钮、点击选择、三维拖动和 5 mm 网格吸附，原有 XYZ 输入继续提供精确定位。约束吸附、零件连接与实时 CAD 实体预览尚待完善。

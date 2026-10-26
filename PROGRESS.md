# URDFTools 项目进度

## 2026-10-25 — 浮动交互栏与固定栏字体缩放

所有共用 `FloatingPanel` 的查看、导入、结构、关节、代码与 CAD 转换交互栏在拖大或半屏放大时按窗口面积比例同步放大标题、正文和控件（上限 2 倍，缩回后还原）。顶部加入明确的 A− / 百分比复位 / A+ 控件，调整外围固定栏字号，选择保存在本机并于重启恢复。Electron C03 烟测实际拖大 Joint 栏：内容缩放从 1.00 到 1.28024，标题高度从 17 到 22 px；点击 A+ 后 CAD 步骤按钮高度从 36 到 39.59 px，第二个独立进程恢复 110% 设置。截图 `artifacts/C03/desktop/cad-font-scale.png`。TypeScript、Vite、前端 shell 2/2、C03 4/4 与 S06 2/2 通过。检查覆盖 1200×800 桌面尺寸，其他分辨率与所有面板组合仍可继续人工核对。

## 2026-10-25 — CAD转换URDF 自动暂存与重开恢复

CAD 导入后在 Electron 用户数据目录保存一份本机 STEP 源副本，编辑中的 Link、Joint、分组、隐藏状态、当前步骤和材料密度自动写入版本化暂存清单。重新启动应用会从暂存副本重新生成零件网格并还原编辑状态；导入新 CAD 替换旧暂存，导入栏可清除暂存重新开始。预览与导出结果需重算，原 CAD 文件不会被改写。TypeScript、Vite 构建、暂存读写/来源不匹配单元测试、真实 Electron 双进程导入→编辑→导出→重开恢复以及 C03 阶段门禁 4/4 均通过。双进程测试确认关节状态、密度、当前步骤与暂存源路径；证据见 `artifacts/C03/desktop/report.json` 和 `artifacts/acceptance/C03.json`。当前仅保存最近一次 CAD 转换草稿，未验证异常断电时最后一个尚未完成的输入事件。

## 2026-10-24 — CAD转换URDF 模块与同会话状态保留

顶部“转换”更名为“CAD转换URDF”。URDF、CAD 转换、评估三个模块现在保持挂载，切换后返回仍保留本次会话拖入的文件和编辑状态；这不是重启应用后的自动恢复。CAD 转换改为模型占主体的全屏工作区：导入、配置 Link/Joint、验证导出三步；步骤 2 的 Link 设置、Joint 设置、关节试转是独立可开关的浮动窗口，沿用 URDF 工作区的拖动、八方向拉伸与半屏放大交互。未完成 Link 分组时 Joint 栏只提示先分组，避免将导入时的临时关节当作正式配置。已确认的可动关节可在试转栏通过滑块带动主 CAD 网格姿态，滑块支持复位。

TypeScript、Vite 项目构建、`git diff --check` 与真实 Electron C03 smoke 均通过。桌面脚本验证导入 CAD 后切到评估再返回仍有原文件，关节试转改变模型姿态矩阵，后续 2 Link/1 Joint ROS ZIP 导出与 MuJoCo 校验通过。证据见 `artifacts/C03/desktop/report.json`。该图形验收使用原创两零件夹具；用户大型 STEP 的完整 42 关节设置和全部浮窗组合仍需人工体验复核。

## 2026-10-24 — 参照录屏改造 CAD→URDF 转换交互

按用户提供的约 400 秒 CAD2URDF 操作录屏，将转换页改为导入 CAD、整理 Link、可视化设置关节、验证导出四步。零件选择与基座指定保留在同一页；关节页支持在三维零件上点击连接位置、选择圆柱面转轴候选、逐个确认，精确轴/原点/限位/驱动参数收进可展开区域。源单位、SHA-256 与格式转换损失在导入后继续可见。确认后的 URDF 预览现由原始 STEP 三角化为 STL 可视网格；编辑期间的零件选择仍使用可点击的轻量包围盒。小尺度 CAD 自动取景修正。导出结果展开后显示各 Link 的 CAD 实体质量、质心与惯量；未确认密度或活动关节驱动参数继续拒绝物理导出。界面明确只声称 ROS 包与 MuJoCo 已交叉验证，不声称全软件兼容或训练就绪。

项目锁定 Node 的 TypeScript/Vite 构建、`git diff --check`、Electron C03 双零件 STEP→修改转轴→确认→URDF/ROS ZIP 导出与独立 MuJoCo 校验通过；转轴 Z→X 后四元数变化、输出 2 Link/1 Joint、总质量 0.003348 kg。CLI 检查预览为两件真实 STL 且无视觉 box；桌面烟测还在三维视图对零件发送实际点选事件，连接点位置随之更新。桌面截图和日志在 `artifacts/C03/desktop/`。该样本是原创两零件夹具；尚未用用户真实大型 CAD 装配或其他仿真软件验证。旧 M01 建模桌面 smoke 的入口仍引用已合并前的“建模”顶栏，当前运行在入口处失败，不能据此声称该旧验收通过。

## 2026-10-24 — 查看器 A1 贴图、深色网格和物理地面桌面复验

用用户此前导入的 23 Link / 22 Joint A1 包，以及 WMP 的 24 Link / 23 Joint A1 包，在隔离的 Electron 桌面实例中重新导入并实际截屏。两者均解析 13 个 DAE 网格实例及 1 个贴图表面；用户包中的碳纤维纹理和 Unitree 标识可见，视觉模型开关切换后网格保持深色，界面无资源告警或崩溃。修复了贴图经自定义协议加载失败、受光照材质导致整机泛白，以及结构图拖动时的空指针异常；记录渲染/资源/进程错误供后续定位。

“受重力影响”现从导入 URDF 的碰撞体与惯量建立 MuJoCo 无驱动模型，增加与可见网格同处 z=0 的物理平面；仿真使用 -9.81 m/s²，真实接触后同步自由基座和全部 12 个活动关节。用户 A1 包在 4.8 秒仿真后报告 11 处地面接触，画面显示整机在地面上且相机自动重新取景；WMP A1 亦报告 6 处接触，仍有轻微运动时明确显示“仍在运动中”。因为没有关节驱动和控制器，四足机器人可能倒向侧面，这符合被动落地而非站立控制。此功能是一次有接触的下落预览，不是连续实时仿真。TypeScript、Vite、Python/Node 语法与差异检查通过；两份真实 A1 桌面导入/查看/重力流程退出 0。构建提示的大 chunk 及 VA-API 初始化失败仍出现，但在上述图形复验中没有造成贴图缺失或退出。

## 2026-10-24 — A1 贴图白屏与崩溃修订

用户重新运行桌面应用后仍报告 A1 整机发白和一次未知崩溃。检查最新导入记录 `1930f24c-870c-4e0a-be43-8cb7778648fb`：5 个 DAE、1 张 PNG、URDF 与报告大小和 SHA-256 一致，导入 finding 为空，问题仍在渲染阶段。将贴图通过协议读取后转换为本地 Blob URL，避免图像加载器直接读取自定义协议；相同 DAE 只解析一次，实例共享几何以降低内存；修复结构图拖动状态更新可能读取已清空指针造成的异常；桌面终端记录资源请求、渲染控制台错误和渲染进程退出原因，界面显示资源错误。TypeScript、Vite 构建、Node 语法和差异格式检查通过。尚未完成 Electron A1 实际目视复验，不能宣称白屏与崩溃已彻底解决。VA-API 日志为视频硬件加速初始化失败，现无证据表明它是 DAE 贴图或崩溃原因。

## 2026-10-23 — 查看模块结构图与材质修订

依据用户 A1 实际截图和最近一次导入记录（5 个 DAE、1 张 PNG 已复制，资源检查无 finding），将 DAE 加载地址绑定到导入资源记录，并显式设置同目录贴图路径；显示网格实例/贴图表面数及实际加载错误。降低过强环境光和主光，设置色调映射，保持地面接收阴影，以处理整机和网格发白。结构栏由缩进列表改为 Link/Joint 节点图，支持连线、点击选择、平移、缩放和适合视图。所有查看页浮动窗口增加半屏放大/还原。TypeScript 无报错、Vite 临时目录构建成功；本轮未运行 Electron 图形端实际复验，A1 贴图和最终亮度仍需用户在更新后的应用窗口确认。

## 2026-10-23 — 查看模块网格、落地与浮动窗口

按用户 A1/Go2 截图修复“选择 URDF 文件”只复制 XML、漏掉相邻 meshes 与 DAE 贴图的问题；导入报告列出网格/贴图数，缺少 package.xml 时仅唯一资源路径可绑定。查看器默认按视觉最低点贴地，增加可选 MuJoCo 2.5 秒无驱动重力下沉；后者是一次仿真预览，不等同于实时控制。关节点可拖动转动，关节点/结构树/滑杆红色联动，Link 点击有红色包围框；结构树展开折叠。文件、显示、结构、关节、物理、测量面板独立浮动，可拖动缩放。设计与边界见 `docs/VIEWER_INTERACTION_2026-10-23.md`。TypeScript/Vite 构建、Python 语法与差异格式检查通过；桌面真实模型端到端运行尚未执行，不能宣称材质和重力效果已验证。

## 2026-10-23 — MyHIMLoco / WMP 原始训练目录导入

读取本机两套训练项目的入口代码、实际 `config.json`、TensorBoard 日志、URDF 网格与回放目录，映射见 `docs/NATIVE_TRAINING_IMPORT.md`。结果工作台增加原始目录入口：按配置定位 URDF，读取至多 8 个 TensorBoard 文件及训练目录中至多 4 段视频，也可另选外部视频目录；训练检查点不反序列化。缺少独立评估时明确记录为缺失，对比仍可建立描述性 Agent 请求，但不生成成功率或置信区间。原有严格实验包入口保留。TypeScript/Vite 构建与 Python 语法检查通过；本轮未运行导入端到端测试。其它算法目录、非四足类别、独立评估语义映射和视频画面供 Agent 直接分析尚未完成。

## 2026-10-23 — 开源前端技能与结果项目工作台

检索 Anthropic、Vercel、UI UX Pro Max 的前端技能，以及 urdf-loaders、URDF Studio、step2urdf、FreeCAD、React Three Fiber、Aim、TensorBoard、Flowise 等界面与交互实现；在个人 Codex skills 目录安装 frontend-design、react-best-practices、ui-ux-pro-max。来源与取舍见 `docs/UI_RESEARCH_2026-10-23.md`。结果工作台加入项目命名和标准标记、算法分组、候选项目对同算法标准的逐项卡片、双 URDF 同网格场景、视频和标量曲线；对比卡与 Agent 请求编号持久化，重新打开候选项目可恢复。URDF 查看画布加入点选 Link；CAD 工作台增加零件包围盒点选和 Base 选择；建模工作台增加素材按钮、三维拖动与 5 mm 网格吸附。每组结果可创建带来源哈希与引用校验的 Agent 请求，网页模式由用户交接，CLI 模式须显式选中后运行。TypeScript/Vite 生产构建通过。通用散文件导入向导、Agent 视频画面分析、真实 CAD 网格与约束吸附仍需后续实现，不宣称本轮完成。

## 2026-10-23 — 四模块界面与交互第一轮重做

按用户截图将查看和转换的三维场景提升为主区域：查看页导入/结构/关节/物理分栏，转换页左侧配置与右侧实时预览，建模页生成后优先显示预览，评估页统一实验与视频卡片。增加项目内 `urdf-ui-workbench` 技能，核对本地锁定的 step2urdf 截图及 urdf-loader 文档。TypeScript/Vite 构建、前端 shell 2/2、S06 Go2/G1 真实桌面 2/2、C02 STEP 桌面 2/2、M01 建模桌面 2/2 均通过。详见 `docs/UI_WORKBENCH.md`。Q01 许可门禁仍未完成，本轮未宣称最终打包。

## 2026-10-23 — D03 Agent 双模式接入复验

在既有网页 WebCodex 流程上新增桌面「打开 ChatGPT 并复制请求」及 3 秒状态回查，用户仍需在网页对话主动粘贴发送；恢复可选的当前账号 Codex CLI 分析和建模模式，只有明确选中并点击运行才发送受限诊断摘要或完整 CAD 参数配方。两种模式使用不可变请求、来源版本校验、证据引用校验与独立 CAD 预览；不能自动应用。CLI 请求与网页请求有不同 provider 绑定，不能互相代提交。真实 ChatGPT 登录的 CLI 在合成 URDF 夹具上首轮回复不合 Schema，已被拒绝；加入结构化输出约束后同一夹具真实复验通过，生成五类原因、advice_only 且无模型改动。TypeScript/Vite 构建通过，正式 D03 4/4 gate、23 项单元及 Electron 双模式请求烟测通过。此结果不代表用户真实机器人性能或无人值守网页模型 API。详见 docs/acceptance/D03.md。

## 2026-10-23 — Q01 便携发行技术候选，正式 gate 3/4（许可阻塞）

本轮先经指定 WebCodex 插件只读核对 Runner/作业/锁/最近源码写入，无并发写入，保留原有未提交改动。从 Q00 已通过的真实仓库继续 Q01。实现自带 CPython 3.12.14、五套 Python worker venv、Electron 39.2.7、前端和原创两连杆示例的 Ubuntu x86_64 `.tar.zst` 便携包，启动时修复 venv 重定位，不依赖 Codex CLI/缓存；桌面新增「打开内置示例」真实导入入口。最新归档 **642908487 字节**，SHA256 `53f8f196aa11ffa8fa61157bc1f07b7328caa7283177e74599839c01396ac92a`；74 个 Electron 文件哈希一致，解压到新目录 + 干净 HOME + 无效外部代理，实际 Electron/CPython 导入并显示 **2 link / 1 joint / 2 mesh**，sandbox/contextIsolation 通过，随包 CLI doctor 成功。最初 GUI smoke 有异步时序失败，已修复并复验。正式 `.venv/bin/python scripts/accept_phase.py Q01` **3/4 gate 通过、1 failed、0 skipped**：108 个 Python 发行包审计仍有 **7 项缺失随包许可文本**，原生依赖再分发许可和 FreeCAD 外部桥未完成，因此 **Q01 不标记完成、候选包不可公开分发**。没有验证真正断网、干净 Ubuntu 机器、GNOME 收藏夹、AppImage 或用户真机。证据 `docs/acceptance/Q01.md`、`artifacts/acceptance/Q01.json`、`artifacts/Q01/`；下一轮先完成许可审查及 Q01，再推进 Q02。未改 `.scheduler/state.json`、未 push。


## 2026-10-23 — Q00 跨模块端到端技术验收 3/3

确认 WebCodex 无其他运行作业/活跃锁，保留全部历史未提交改动。新增 Q00 真实 Electron 联合烟测：从原创两零件 STEP 经 CAD 向导导出 URDF/ROS ZIP，重新导入、2 mesh/2 link/1 joint 查看及关节旋转，静态扫描 0 finding，独立 MuJoCo floating-base 总质量 0.003348 kg；另经真实建模 UI 改尺寸、撤销/重做及导出。负例覆盖零关节轴、ZIP 穿越、缺 STL、坏 ZIP、拒绝无权限文件；新 worker 重启恢复与未完整 IPC 请求取消无残留。离线不可用代理下本地 Electron 查看成功。正式 `.venv/bin/python scripts/accept_phase.py Q00` **3/3 gate 通过、0 failed/0 skipped**，TypeScript/Vite 生产构建成功。首轮缺 Node PATH 失败后改用项目固定 Node，失败记录保留。证据 `docs/acceptance/Q00.md`、`artifacts/acceptance/Q00.json`、`artifacts/Q00/`。限制：中途拷贝取消/恢复未覆盖、测试 STEP 为原创夹具而非用户机械装配、无真机/真实训练数据；下一阶段 Q01 离线发行及许可清单。


## 2026-10-23 — D03 正式验收通过：网页 ChatGPT 通过 WebCodex 驱动 Agent

用户不再使用额度已耗尽的本地 Codex CLI 模型，改用已连接 @web-codex-tunnel 的网页 ChatGPT 对话。新增不可变请求队列、受限证据工具、用户导入 URDF 本地静态诊断、CAD 建模版本与 SHA256 校验、独立预览与人工应用，桌面 Agent 侧栏、建模按钮及 Electron 受控 IPC 已接通，并从 UI 下线原 Codex CLI `agent-suggest` 入口。当前网页 ChatGPT 会话通过 WebCodex 实际完成 1 份证据约束诊断建议和 1 份 20→25mm Leg 单变量 CAD 建模预览，原模型 revision 1 未改变；并真实测试 Electron 请求生成、复制及回查。正式 `.venv/bin/python scripts/accept_phase.py D03` **4/4 gate 全过、21 项单元测试，0 failed/0 skipped**，无本地 Codex CLI 模型调用。证据见 `docs/acceptance/D03.md`、`artifacts/acceptance/D03.json` 和 `docs/WEBCODEX_AGENT_GUIDE.md`。这是**网页对话需用户主动交接**的模型辅助，不是桌面自动调用后台 ChatGPT 推理 API；示例结果不能视为真实机器人验证。D02 重新生成报告后有 1 份历史诊断请求对应的上游哈希变化：已保留历史响应并显式提示需重新请求，绝不冒充最新 CAD 结论。下一阶段 Q00 端到端回归与桌面发行。

## 2026-10-23 — D03 证据归因强化与代理网络复验

确认 WebCodex Runner 无项目作业、Git index 锁、活跃调度器持锁或近 10 分钟源码写入，保留既有未提交工作。修复 D03 推荐项可引用其他竞争原因证据的问题：建议只能引用其对应原因已登记的支持证据；新增误把 E04 控制仿真证据引用为机械设计依据的拒绝测试，现 **7/7 单元通过**，编译与 `git diff --check` 通过。发现本机代理 `127.0.0.1:7892` 正在监听，尝试显式 HTTPS_PROXY/HTTP_PROXY/ALL_PROXY；ChatGPT 登录有效、HTTP HEAD 可达，但模型请求仍返回 TLS/WebSocket 传输错误。正式 D03 仍 **1/2 gate，1 failed，0 skipped**，记录 `artifacts/D03/runs/20261023T040401566017Z/`，不伪造模型答复或将 D03 标记完成。下一步修复 Codex 实际网络路由后复验，再推进 Q00。


## 2026-10-23 — D03 Agent 证据引用防护实现，真实登录生成阻塞

实现证据受控检索、五类竞争因素完整引用/反证校验、仅人工确认的候选建议和真实 ChatGPT Codex CLI 只读调用；六项拒绝伪造证据/漏反证/自动 CAD 修改的测试通过。正式 D03 gate **1/2 通过、1 失败、0 skip**：ChatGPT 登录凭据有效，但最小化模型请求和正式请求均因 chatgpt.com TLS/WebSocket EOF 失败，未获得真实模型答复，不伪造建议与完成状态。见 docs/acceptance/D03.md、artifacts/acceptance/D03.json；恢复 Ubuntu 到 ChatGPT 的真实 TLS 连通后必须重跑 D03。

## 2026-10-23 — D02 机械组报告和真实 FreeCAD 零件映射

续做 D01 既有成果，完成只读诊断证据索引与明确审阅的 CAD part→URDF link/joint 映射、跨来源证据禁止归因、未匹配拓扑提示及存在性/哈希校验的本地视频和指标链接。真实 FreeCAD M02 风格 base/resized/topology 导出 STEP、OCP 检测 ArmLink 变化，BaseBracket 未匹配，中文 HTML 和 PDF 生成成功。保留无效 evidence:d00 与独立来源不相干的证据为 unknown，未称用户机械实际验证。正式 D02 **3/3 gate、6 项单元、0 skip**。证据 docs/acceptance/D02.md、artifacts/acceptance/D02.json、artifacts/D02/；下一阶段 D03 Agent 只读证据建议。

## 2026-10-23 — D01 单变量 CAD 消融与外部复验建议

基于 build123d/OCP 实际 B-rep 生成 100→120 mm 单变量腿长变体，重算质量 0.054→0.0648 kg、Iy 4.545e-5→7.83e-5 kg·m²、COM、碰撞盒及远端 joint frame；MuJoCo 3.16 真实编译 1 DOF，两份模型动态质量一致，固定 root 惯性被导入器丢弃已显式记录。外部复验读取磁盘结果并核对 hash、配对种子、协议和独立审核门禁；合成成绩不能升格为观察效果。正式 D01 **3/3 gate、5 项单元、0 skip**；D00 回归 2/2、4 项测试通过。见 `docs/acceptance/D01.md`、`artifacts/acceptance/D01.json`、`artifacts/D01/`。真实外部训练/用户 CAD 变体与 B00 审核集成仍缺失；下一阶段 D02 CAD 部件映射和机械组报告。

## 2026-10-23 — D00 受证据约束诊断图验收

新增症状→来源证据→五类竞争因素→复验动作的确定性诊断图，联接 K01/K02 真实模型技能、B08 外部结果和 E04 MuJoCo 控制器探测。正式 D00 **2/2 gate、4 项测试、0 skip**；synthetic_fixture 性能差不认定机械设计缺陷，足底碰撞缺失给局部描述问题，奖励/协议冲突禁排名。详见 `docs/acceptance/D00.md`、`artifacts/acceptance/D00.json`。下一阶段 D01 外部受控复验建议和结果闭环。

## 2026-10-23 — B08 两类机器人外部结果与视频端到端验收

四足 A1/自有模型、人形 G1/自有模型共 4 份合成实验包真实经过 Electron 入口、哈希资产库、规范化指标/种子结果、协议比较和视频帧时间关联；重启后恢复并在界面并排播放视频。正式 B08 **2/2 gate、3 项后端测试、4 次 Electron 导入、0 skip**；见 `docs/acceptance/B08.md` 与 `artifacts/acceptance/B08.json`。真实已审核参考成绩仍为 0，所有视频/成绩均为 synthetic_fixture；下一阶段 D00 证据约束诊断。

## 2026-10-23 — 本地预览修复与 B08 开发中

`apps/web/index.html` 是 Vite 源码入口，不能用 `file://` 直接运行；已启动并核验 `http://127.0.0.1:5173/` 本地预览，补充浏览器预览提示、禁用需要 Electron 的导入按钮，修正桌面启动脚本执行权限。前端 2/2 测试和生产构建通过；Electron `--smoke` 证实页面渲染、本地服务和隔离预加载接口可用。B08 新增桌面外部结果库选择入口与本地 worker，**3 项后端测试通过**：四足/人形的标准模型与自有模型合成结果包共 4 份可按哈希入库并在重启后查询，独立进程 JSON 接口可用，篡改 URDF 被拒；这些是合成夹具，不是真实参考成绩。视频与 run 的数据库关联、两组 run 的界面比较及 B08 正式 gate 尚未完成，**B08 仍在进行中**。操作契约见 `docs/RESULTS_IMPORT_GUIDE.md`。

## 2026-10-23 — B07 本地视频与指标事件对照

完成 PyAV 真实解码的帧时序/缺帧/偏移检查、报告 CLI，以及 Electron 评估工作区中的本地视频 SHA 核对与事件点击定位。正式 B07 **2/2 gate、2 项媒体测试、真实 Electron 视频播放和前端生产构建通过**；首轮 CSP 阻挡 blob 视频后只增加媒体源规则并复验。证据 `docs/acceptance/B07.md`、`artifacts/acceptance/B07.json`、`artifacts/B07/desktop/media-view.png`。大于 128 MiB 视频的界面核验和 B01 数据库直连仍待后续迭代；不从视频推断扭矩/能耗。下一阶段 B08 两类结果包完整烟测。

## 2026-10-23 — B06 外部日志适配与交换

新增版本化 SB3 CSV、RSL-RL/Isaac Lab TensorBoard tag 映射及本地 MLflow 三列指标交换。正式 B06 **1/1 gate、2 项端到端测试、0 skip**；SB3 格式夹具和 TensorBoard 官方写入器文件经 B00/B01 入库，MLflow 本地往返值/时间一致，未映射字段显式报告。详见 `docs/acceptance/B06.md`、`artifacts/acceptance/B06.json`。未运行上游训练器或验证真实用户成绩；下一阶段 B07 视频时序与交互对照。

## 2026-10-23 — B05 外部结果公平对照与统计

完成固定配方/有界调参分轨、奖励/算法/任务/预算/地形协议核对及独立训练 seed 层统计。正式 B05 **1/1 gate、3 项测试、0 skip**；已知夹具差值 0.25，显式配对 CI `[0.25,0.25]`，单 seed 无 CI，缺失 run 禁排名。见 `docs/acceptance/B05.md`、`artifacts/acceptance/B05.json`。真实参考成绩仍为零，下一阶段 B06 外部日志适配。

## 2026-10-23 — B04 地形与推扰条件协议

完成五类地形、物理/腿长比尺度、明确单位、生成器版本、推扰条件、训练/测试 seed 和成功定义的校验与逐字段可比性报告。正式 B04 **1/1 gate、3 项测试、0 skip**；合成 4 集中 3 成功得 0.75，seed 泄漏、版本/尺度冲突和推扰差异被明确报告。见 `docs/acceptance/B04.md`、`artifacts/acceptance/B04.json`。下一阶段 B05 分层统计与公平对照。

## 2026-10-23 — B03 人形外部结果语义

完成左右足支撑/摆动区间、躯干倾角、左右占空差和可选准静态 COM 投影；G1/H1 29/19 可动关节及动作映射实际校验，G1/H1/用户人形 URDF 与外部合成结果按哈希关联。正式 B03 **1/1 gate、4 项测试、0 skip**；缺传感数据保持 unknown，准静态覆盖不宣称动态平衡。见 `docs/acceptance/B03.md`、`artifacts/acceptance/B03.json`。下一阶段 B04 地形/扰动条件协议。

## 2026-10-23 — B02 四足外部结果语义

完成显式四足足端映射、接触占空比/步频/滑移/跟踪/跌倒的确定性计算，以及 A1/Go2/用户 URDF 的精确哈希结果关联。正式 B02 **1/1 gate、4 项测试、0 skip**；无外部测量时扭矩、滑移或接触指标保持 unknown，合成结果不升格为参考成绩。见 `docs/acceptance/B02.md`、`artifacts/acceptance/B02.json`。下一阶段 B03 人形结果语义。

## 2026-10-23 — B01 外部指标结果入库

完成 B00 原始资产后的 CSV/JSON/Parquet/TensorBoard 标量读取和事务性规范化结果库。四种真实文件格式均解析出相同数值与时间戳；源 SHA、单位、来源、算法/协议与可缺字段状态可追溯，旧 v0 输入显式迁移且原字节保留。正式 B01 **2/2 gate、4 项单元、0 skip**；NaN、缺单位、哈希损坏、重复 run、pickle 均拒绝。详见 `docs/acceptance/B01.md`、`artifacts/acceptance/B01.json`。视频与可比性及真实参照成绩仍在后续阶段。

## 2026-10-23 — B00 外部结果导入可恢复作业

完成 SQLite WAL 租约队列、分块断点、SHA-256 资产库、bundle/机器人身份绑定、取消与完整导入后单次发布。正式 B00 **2/2 gate、3 项单元、0 skip**；进程级验收在 1000 字节检查点后真实杀死 worker，再由新 worker 接管，完成后只有 1 run/1 asset。首次测试导入路径失败已修正，失败与成功日志均保留。见 `docs/acceptance/B00.md`、`artifacts/acceptance/B00.json`。下一阶段 B01 是外部训练结果 manifest、指标和视频语义导入；不开发 RL 训练器。

## 2026-10-23 — K02 G1/H1 人形结构与准静态支撑技能

新增白名单 humanoid_urdf 技能：G1/H1 关节链、膝踝限位、足底碰撞、声明质量/惯量与 q=0 根坐标系质心；可选带显式来源标签的世界系接触多边形/COM/躯干姿态/膝踝时序检查。真实固定厂商 G1 131 pass/0 fail/4 unknown、H1 91 pass/0 fail/4 unknown，质量标签求和 35.11514202/59.338 kg（不是硬件称重）；合成 H1 右踝碰撞缺失检测到 fail。正式 K02 **2/2 gate、11 项 unittest + 厂商技能流程、0 skip**；K00/K01 回归及 TypeScript/Vite 生产构建通过。首轮因 G1 修订文件和 CRLF 字节哈希不一致失败后已修复，失败日志保留。详见 docs/acceptance/K02.md、artifacts/acceptance/K02.json、artifacts/K02/humanoid-report.json。没有真实步态/电机/训练数据，动态稳定性始终 unknown；下一阶段 B00 外部结果库作业基础（不开发 RL 训练器）。

## 2026-10-23 — R02 G1/H1 人形参照模型技术验收

固定 Unitree 官方 commit `5994d4fa`，新增 H1 无手原始 URDF、21 个 STL、上游 package.xml，共 23 文件全部通过 Git blob SHA-1 与 SHA-256 核验；沿用 G1 原始 29-DOF 资源。G1/H1 分别 40/39 与 25/24 Link/Joint，关节分组 12/14/3 与 10/8/1。原始 MuJoCo 解析拒绝后独立派生保留全部碰撞/惯量、移除 36/24 个 visual，G1 重定位 25 个 collision mesh；真实 MuJoCo 编译 29/19 DOF，原始 Electron 查看/关节/碰撞/截图均通过。首次 G1 路径重复失败已修复并保留日志。R02 正式 **3/3 gate、4 项单元、0 skipped**，见 `docs/acceptance/R02.md`、`artifacts/acceptance/R02.json`。无真机或训练性能验证；下一阶段 K02。

## 2026-10-23 — K01 四足结构与准静态接触评估技能

基于已固定来源的 Unitree A1/Go2 原始 URDF，新增四足腿链、12 DOF、足端碰撞、关节轴/限位/effort/velocity 规则及中点姿态足端 FK/凸包几何；缺失电机标定和动态步态保持 unknown。支持显式带来源标签的 COM/接触时序准静态投影检查，但只使用合成时序做正反例，不冒充真实机器人测量。正式 `.venv/bin/python scripts/accept_phase.py K01` **2/2 gate、9 项单元与厂商源技能流程通过，0 skipped**；A1/Go2 各 60 pass/0 fail/2 unknown，合成足端碰撞缺失负例 1 fail。K00 回归 2/2、8 项单元通过；Python 编译、diff 检查与 Electron 生产构建通过（首次缺 PATH 修正后通过）。详见 `docs/acceptance/K01.md`、`artifacts/acceptance/K01.json`、`artifacts/K01/quadruped-report.json`。下一阶段 R02 G1/H1 或 K02 人形技能；技能桌面/MCP 接入与真实动态数据仍未完成。


## 2026-10-23 — K00 本地技能机制与动力学基础

新增仅加载 JSON manifest 的受约束技能注册表，四项基础数值规则覆盖惯量、坐标、接触和样本统计；用户本地新技能可发现和执行，拒绝未知工具/字段/符号链接/非有限输入。正式 `.venv/bin/python scripts/accept_phase.py K00` **2/2 gate、8 项单元 + 4 项实际数值 smoke 通过，0 skip**；首次非 editable Python 路径失败已修复，历史日志保留。证据 `docs/acceptance/K00.md`、`artifacts/acceptance/K00.json`，使用说明 `docs/SKILLS_GUIDE.md`。目前仅 Python API，未接入 Electron/MCP，尚非四足/人形真实验证；下一阶段 K01 或 R02。


## 2026-10-23 — R01 Unitree A1/Go2 厂商资源和 MuJoCo/Electron 双链路验收

复用已有 Unitree 固定 commit 的 A1 和 Go2 原始 URDF/DAE/许可记录，不改原文件；真实资源导入与 Electron 3D 查看器 (A1 23 Link/22 Joint，Go2 42/41) 全部通过。MuJoCo 原生编译 A1 12 DOF，Go2 原始重复 material 被拒绝，因此明确生成仅供仿真的无视觉派生副本（移除 17 visual），编译 12 DOF 并记录损失/hash。R01 首轮独立临时目录测试发现路径报告问题后已修复，正式 **3/3 gate、3 项单元 + 两套真实 Electron E2E 通过**。见 docs/acceptance/R01.md、artifacts/acceptance/R01.json；后续 R02 G1/H1 与 K00 技能机制。

## 2026-10-23 — R00 模型版本注册表与不可变 SHA256 本地缓存

已实现 SQLite WAL 模型版本/来源/许可记录、哈希资产缓存、同名多版本和审核后发行门禁，以及本地 CLI；同版本冲突不覆盖，下载失联不污染记录，synthetic_fixture/user_upload 无法被自动打包。正式 R00 **2/2 gate、4 项测试 + 实际 2 版本 CLI 流程通过，0 skip**；测试并非在线用户生产库与真实参考实验。见 docs/acceptance/R00.md、artifacts/acceptance/R00.json。下一阶段 R01/R02 厂商参照资产整包注册或 K00 技能系统。

## 2026-10-23 — E04 无训练仿真动态探测和时序回放

真实 MuJoCo 3.16 CPU 执行单关节阶跃、错误负阻尼对照、短脉冲恢复、自由体落地接触、25 姿态扫掠、浮动四足站立探测和从仿真 qpos 生成的 30 帧示意 GIF。真实记录错误 PD 末态误差 2.687 rad 对正确 PD 7.61e-8 rad；落球 1066 接触步，四足站立样例失稳（绝非站立成功）。正式 E04 工具验收 **2/2 gate、4 项测试通过**，无真实训练或机械因果结论。证据 docs/acceptance/E04.md、artifacts/acceptance/E04.json、artifacts/E04/probe-report.json。后续可按依赖推进 R00 参照模型注册表与 K00 技能机制。

## 2026-10-23 — E03 MuJoCo 编译与来源/映射/质量损失审计

新增只读转换编译审计：真实 MuJoCo 3.16 对 E00 的九份原创 URDF 6 接受、3 拒绝；四足 8 DOF/3.2 kg 动态质量（源 11.2 kg）、人形 4 DOF/7 kg（源 19 kg），明确报告根 Link 固定后失去独立动力学质量和固定传感器 frame 合并。E03 正式 **2/2 gate 通过，4 项合同测试，0 skip**；无自动惯量修补，不宣称适用 RL。见 docs/acceptance/E03.md、artifacts/acceptance/E03.json；下一阶段 E04 无训练探测。

## 2026-10-23 — E02 双连杆解析动力学与真实 MuJoCo 多姿态对账

已实现独立二维双连杆质量矩阵/重力项公式并实际对比 MuJoCo 3.16 的 3 份原创模型、4 组姿态，正常最大质量/重力误差约 1e-16，错肘关节 frame 导致约 0.24 kg*m² 和 6.15 N*m 差异，固定无惯量传感器 frame 无假阳性。首次因新 MuJoCo API 签名失败，修复后正式 E02 2/2 gate、3 项数值测试通过；未声称真实机器人验证。见 docs/acceptance/E02.md 和 artifacts/acceptance/E02.json。下一阶段 E03 转换与映射校验。

## 2026-10-23 — E01 静态语义与物理规则

新增可复用只读 URDF 静态检查与 CLI，输出带规则版本、来源 SHA-256、对象位置、数值/单位、可信设计上下文和复核动作的 Finding。九份金标准对应 5 条错误，2 个边界反例无误报；缺少设计 sidecar 不将合法非零关节轴/视觉尺寸判为确定错误。正式 .venv/bin/python scripts/accept_phase.py E01 **2/2 通过**（5 项单元 + 9 个 CLI 实际扫描），0 skipped。见 docs/acceptance/E01.md、artifacts/acceptance/E01.json。下一阶段 E02。

## 2026-10-23 — E00 评估协议与九个金标准故障/合法反例

继续已有 E00 WIP，登记正式验收入口；4 项原创数值/结构测试通过，真实 MuJoCo 对 9 份 URDF 编译判断符合预期（6 接受、3 拒绝），正式 .venv/bin/python scripts/accept_phase.py E00 **2/2 gate 通过，0 skip**。评估结果仅针对自制夹具和 MuJoCo 编译语义，不能作为真实机器人性能证据。详见 docs/EVALUATION_PROTOCOL.md、docs/acceptance/E00.md 和 artifacts/acceptance/E00.json。下一阶段 E01 静态语义和物理规则。

## 2026-10-23 — M02 FreeCAD 回流与版本差异验收通过

真实 FreeCAD FCStd 改名/尺寸/拓扑变体经 STEP 回流；零件可重关联，新增孔导致的拓扑变化产生冲突且不覆盖用户 Link/关节编辑。Electron 人工接受后关节确认清零，重启恢复已接受 STEP/hash/配置。`.venv/bin/python scripts/accept_phase.py M02` **2/2 gate 通过**；C04 3/3、M01 2/2 回归通过。详见 `docs/acceptance/M02.md` 和 `docs/MODEL_RETURN_GUIDE.md`。下一阶段按依赖推进 A00 Agent 工具层或 E00 评估方法。

## 2026-10-23 — M01 建模工作台验收通过

已实现 Electron 建模工作区、命名 STEP 装配桥、关节轴显示、空配方新增零件/镜像/撤销重做、C02/C03 预览和导出连接。正式 `.venv/bin/python scripts/accept_phase.py M01` **2/2 gate 通过**：真实双连杆 STEP→URDF ZIP→MuJoCo，Electron 从空项目完成新增、位移编辑、撤销/重做、关节确认、预览、导出；版本恢复核对资产哈希。M00 3/3、C02 2/2、C03 4/4 回归通过，生产构建通过。详见 `docs/acceptance/M01.md`。下一阶段 M02 FreeCAD 往返与版本差异；镜像目前仅对称复制位置，任意不对称几何的真正镜像仍有限制。

## 2026-10-22 — M00 参数化 CAD 核心验收通过

build123d 0.13.0 独立建模 worker 已实现允许列表配方、草图/拉伸/旋转/布尔/圆角、材料密度、STEP/STL、精确质量惯量和不可变版本事务。`.venv/bin/python scripts/accept_phase.py M00`：**3/3 gate 通过，0 failed，0 skipped**；支架与两连杆、参数重算、错误草图回滚的真实测试通过。详见 `docs/acceptance/M00.md`、`docs/MODELING_GUIDE.md`。下一阶段 M01 交互式建模界面；评估模块仍未实现。


## 2026-10-22 — C04 Ubuntu FreeCAD/IGES/BREP 互通验收通过

按用户要求改为 FreeCAD 优先。本机官方 FreeCAD 1.1.4 AppImage 通过 SHA-256 校验，FCStd→STEP 的真实无头导出与桌面入口均运行通过；IGES/BREP 闭合实体桥保留并覆盖显式单位、几何损失报告和开放曲面拒绝。`.venv/bin/python scripts/accept_phase.py C04`：**3/3 gate 通过，0 failed，0 skipped**，含 5 个真实 CAD 文件流程测试及 Electron E2E。C02 2/2、C03 4/4 与生产构建回归通过。详见 `docs/acceptance/C04.md`、`docs/CAD_EXCHANGE_GUIDE.md`。下一阶段可推进 M00 建模核心；训练结果评估仍未实现。


## 2026-10-22 — C03 STEP 到 URDF/ROS 包技术验收通过

独立导出闭合 STEP 实体的 STL 视觉网格、物理惯量、显式密度和驱动限值；ZIP/目录可重新导入。MuJoCo 独立编译原始固定基座及注入自由关节的浮动基座模型，明确报告固定根质量排除和训练未就绪。真实 ROS 2 colcon 安装包可重新导入，Electron UI 完成实际导出。

`.venv/bin/python scripts/accept_phase.py C03`：**4/4 gate 通过，0 failed，0 skipped**。详见 `docs/acceptance/C03.md`、`docs/CAD_EXPORT_GUIDE.md` 和 `artifacts/acceptance/C03.json`。下一阶段按任务依赖开展建模/评估模块；旧调度器状态不再作为进度依据。


## 2026-10-22 — C02 关节分组与转换向导完成技术验收

实现真实 STEP 读取与单位/装配一致性核对、圆柱面轴线候选、可编辑 Link 分组及单根父子树、关节类型/轴/原点/限位、人工确认和 SHA-256 绑定的配置复用。Electron“转换”工作区接入独立 CAD worker 与自动三维预览。预览明确仅为视觉包围盒，不含物理属性和最终导出。

实际运行 `.venv/bin/python scripts/accept_phase.py C02`：**2/2 gate 通过、0 failed、0 skipped**；5 个真实 STEP/配置测试和 Electron 端到端均通过。桌面改变关节轴后实际四元数由 Z 旋转变成 X 旋转。S03 4/4、S04 2/2 回归通过，生产构建通过。证据 `docs/acceptance/C02.md`、`artifacts/acceptance/C02.json`、`artifacts/C02/desktop/`；操作说明 `docs/CAD_WIZARD_GUIDE.md`。下一阶段 C03 为精确网格/惯量/URDF-ROS 包导出与交叉验证。


## 2026-10-22 — 切换为每小时直接开发；独立复核 S03–S06、C00–C01

用户取消本地 Python/systemd 调度器。`urdftools-dev.timer` 已禁用，Codex 应用已有每小时心跳已改为在当前对话直接开发。检查 WebCodex runtime 时该项目活跃任务为 0，因此接手现有 WIP。旧 `.scheduler/state.json` 停留 S03 属历史状态，不作为当前进度。

本轮独立运行 `.venv/bin/python scripts/accept_phase.py S03 S04 S05 S06 C00 C01`（逐阶段单独调用），结果分别为 4/4、2/2、2/2、2/2、3/3、3/3，均 0 failed / 0 skipped；S06 真实 Go2/G1 Electron 模型导入与关节操作成功。S02 回归 2/2；固定 Node/npm 路径的 TypeScript 与 Vite 生产构建退出 0；`git diff --check` 退出 0。首次生产构建命令误写为不存在的 `.tools/node/bin/npm`，因路径错误退出 127；随后按 `docs/TOOLCHAIN.md` 使用 `.tools/node/bin/node .tools/npm/bin/npm-cli.js` 重跑通过。

这些 gate 确认目前已实现的导入、查看、STEP 元数据及质量属性功能；不代表 CAD→URDF 转换向导、建模 Agent 或 RL 结果评估已完成。下一阶段按依赖为 C02。第三方 step2urdf adapter LICENSE 的版权占位和完整发行审查仍留给 Q01。


## 2026-10-22 — C01 CAD 质量/质心/惯量与坐标变换技术 gate 通过（等待调度器复核）

实际运行 .venv/bin/python scripts/accept_phase.py C01：**3/3 gate 通过、0 skip**；质量属性数值测试 8/8，CLI 场景 4/4。实现位于 python/urdftools/cad/mass_properties.py，通过 OCP 的闭合有效 B-rep solid 计算体积、质心与惯量，并按显式密度换算 kg 与 kg·m²；使用 \(I_w=RI_lR^T\) 变换惯量张量，并用平行轴定理合成装配总惯量。命令行入口为 scripts/cad_step_mass.py。

独立公式验证结果：20×10×5 mm 长方体、两个偏置半径 10 mm 球体、旋转 45° 的长方体（含非对角 \(I_{xy}=-1.25\times10^{-8}\,kg\,m^2\)）均通过。无材料密度时，质量/物理惯量与装配总值保持 null；近似几何不参与质量计算，OBJ/visual/collision mesh 不作为真实质量来源。详见 docs/acceptance/C01.md 和 artifacts/acceptance/C01.json。

C01 仍是后端 API/CLI，不包含材料数据库、交互式密度分配 UI、CAD→URDF 导出或查看器集成。step2urdf 上游 MIT 许可版权占位符仍需 Q01 复核。按 tasks/C01.md，阶段完成状态待调度器复核；本轮没有修改 .scheduler/state.json 或创建 Git commit。


## 2026-10-22 — C00 STEP 内核与转换原型技术 gate 通过（等待调度器复核）

实际运行 `.venv/bin/python scripts/accept_phase.py C00`：**3/3 gate 通过、0 skip**；STEP 读取契约测试 4/4，CLI 对两个真实 STEP fixture 的检查 2/2。CAD worker 使用独立的 CPython 3.12.14 环境，OCP 8.0.1.1.0 / proxy 8.0.1.1.0 / NumPy 2.3.4 / PyYAML 6.0.3 均由 `cad-requirements.lock` hash 锁定；`pip check` 无依赖冲突，主应用 `.venv` 未安装 OCP。

双零件 mm 装配读取到 1 根装配、2 个零件、两种颜色及第二零件 (0.05, 0.02, 0.01) m 的变换；单零件 m 文件识别为 metre，尺寸归一化约 0.02×0.01×0.005 m，缺失颜色保留为未知。公开 API `urdftools.cad.inspect_step` 与 `scripts/cad_step_inspect.py` 输出源文件 SHA-256、单位、装配树、4×4 变换矩阵、颜色和内核/适配器 provenance。详见 `docs/acceptance/C00.md` 和 `artifacts/acceptance/C00.json`。

C00 仍只是 STEP 读取与元数据原型，**没有**生成 URDF、推断关节、转换 UI、质量/惯量物理验证或 RL 训练结果分析。step2urdf 上游 MIT LICENSE 的版权行包含 `YOUR NAME HERE` 占位文本，Q01 发行许可审查必须处理。按 `tasks/C00.md`，阶段完成状态仍待调度器复核；本轮没有修改 `.scheduler/state.json` 或创建 Git commit。


## 2026-10-22 — C00 CAD 内核预检历史记录（正式技术 gate 前）

独立环境 `.tools/cad-venv` 固定 cadquery-ocp-novtk 8.0.1.1.0 / cadquery-ocp-proxy 8.0.1.1.0 / numpy 2.3.4。首次尝试带 VTK 的 wheel 时实际报 libvtkWrappingPythonCore3.12.so 缺失，随后改用无需 VTK 的固定内核，已经成功导入 OCP 和 XCAF STEP APIs。通过真实 STEP 写入-读取：单根装配/2 组件，包含 30 mm 位移；源长度单位 MM 和 M 都可识别，内部几何 20 mm 转成 SI 应为 0.02 m。
原创 `scripts/generate_c00_fixtures.py` 输出 `tests/fixtures/C00/two_part_mm.step` / `single_part_m.step` 和 hash 清单；原型 `urdftools.cad.step2urdf_adapter.load_step` 直接读取 2 个有颜色、姿态不同的零件，以及 1 个缺失颜色的米单位零件，实测包围盒、名称和 COM 数值正确。详情见 `docs/CAD_KERNEL_PREFLIGHT.md`。当时尚未通过 C00 正式技术验收；后续 gate 结果见上方。转换 UI 和 CAD→URDF 生成仍未实现。没有启动调度器或训练器，没有修改系统 Python/驱动。

## 2026-10-22 — S06：Unitree Go2/G1 真实三维查看端到端验收

WebCodex 主动构建，不依赖定时调度器。首次运行真实 Unitree Go2 文件夹导入时发现旧的 4 MiB URDF/XML 限制误用于 10.7 MB 的合法 Collada DAE 网格。修复为 mesh 使用原有单文件 64 MiB 限额，URDF/package XML 仍保持 4 MiB；不改写用户或上游的源 URDF。随后 S06 `tests/s06/` **3/3** 文件来源/sha256/Go2 文件夹/G1 ZIP 导入测试通过。

正式命令 `.venv/bin/python scripts/accept_phase.py S06` **2/2 gate 通过、0 skipped**。真实 Electron 39.2.7、React/Three.js 和 headless SwiftShader 自动使用原生拖放验证：Go2 **42 Link/41 Joint**、12 可动关节、44 Mesh、27 Collision/27 个红色线框 Mesh；G1 **40 Link/39 Joint**、29 可动关节、73 Mesh、37 Collision/37 个红色线框 Mesh。两者成功加载资产、实测关节姿态改变、Visual/Collision 切换、来源物理字段指纹不变、视角重置、PNG 下载。上游与许可固定版本在 `tests/fixtures/S06/reference_models.json`，机器验收 `artifacts/acceptance/S06.json`、`artifacts/S06/desktop/`，完整指南 `docs/VIEWER_GUIDE.md`、`docs/acceptance/S06.md`。

S06 是只读显示验收，**不是四足机器人 URDF 在强化学习中适用性的结论**；网格包围盒不是 CAD 精确尺寸。CAD→URDF、Agent、物理仿真、外部 RL 训练结果分析和 GNOME 正式安装仍未完成。未运行 RL 训练器、调度器或修改其 state，保留所有 WIP，未 Git commit。

## 2026-10-22 17:16 CST — S05 查看器分析工具验收通过

在保留工作区所有未提交成果的前提下完成 S05：结构树/Link-Joint 定位、视觉与 Collision 独立显示、显式质心标记、Link 隔离/恢复、视角重置、PNG 导出、质量/质心/惯量字段读取和整机/Link 视觉包围盒测量。缺失的 URDF 物理字段保持“未知”，不会将 loader 默认零值当作真实参数。

实际运行 `python scripts/accept_phase.py S05`：**2/2 gate 通过、0 skip**。Python 夹具 2/2；Electron 39.2.7 + headless SwiftShader E2E 验证 2 Link / 1 Joint、1.25 kg 已知质量 + 1 Link 未知质量、碰撞/视觉切换不改变物理指纹、关节 ±1.2 rad 限位、包围盒数值、COM 标记、隔离恢复、视角重置和 PNG 导出。截图 `artifacts/S05/desktop/viewer-analysis.png`，机器报告 `artifacts/acceptance/S05.json` / `artifacts/S05/desktop/report.json`。

随后回归实际运行 S02 **2/2**、S04 **2/2**、S03 **4/4**，均 0 skip；S02 领域测试 28/28、S03 导入测试现为 18/18（新增真实大型 DAE 上限回归测试）。当前生产构建、Electron 主进程语法检查、`git diff --check` 通过。早先 S05 的失败验收记录保留在阶段运行日志中，修复后的最新 gate 已通过。测试只使用原创合成 URDF，不等同于真实四足机器人验收；包围盒不是 CAD 精确尺寸，物理/动力学有效性、CAD/Agent/训练结果分析和正式安装包仍未实现。未运行强化学习训练；未启动或修改 scheduler/timer/state，未创建 Git commit。


## 2026-10-22 下午 — 网页 ChatGPT + WebCodex 直接构建 S03/S04

用户变更分工：WebCodex 为主要开发通道，任务调度器只用于阶段性成果复核和改进；此次没有启动/修改 scheduler、timer 或 `.scheduler/state.json`。
接管时 S03 已有保留的未提交代码。初次 `python3 scripts/accept_phase.py S03` 结果 3/4：17/17 导入测试、CLI 真实工作流、React SSR 通过；Electron 原生拖放因固定坐标未落入响应区而失败。修复为根据 DOM 实际坐标投递文件夹并输出诊断后，S03 阶段 gate **4/4 通过、0 skip**，包含 Electron 沙箱/IPC/导入选择/缺 Mesh 定位。后续集成 S04 后 S03 再回归 4/4 通过。
S04 已接入固定版本 three@0.180.0、urdf-loader@0.13.1、@types/three@0.180.0，离线方案采用受控 Electron 自定义 `urdftools://asset` 协议与 SHA256 已导入资产核验，不接受任意磁盘路径。React/Three.js Z-up 场景、旋转缩放/平移、OBJ/STL/DAE/基本几何加载、动态关节滑块/限位已经接线；单关节真实浏览器验收会旋转机器人关节。新自制 CC0 夹具 `tests/fixtures/S04/simple_robot`（2 link、1 revolute、OBJ mesh）在真实离线 Electron/WebGL 渲染下，两个 mesh 显示、package URI 加载、shoulder 转到 1.20 rad（上下限 ±1.20 rad）并生成 PNG。S04 声明 gate **2/2 通过、2/2 测试、0 skip**，证据 `artifacts/S04/desktop/viewer.png` 与 `artifacts/acceptance/S04.json`。未测试真实用户四足/humanoid/复杂大型模型，不能宣告 S05/S06 或 CAD/Agent/评估已完成。
已保留第三方依赖来源和许可线索，发行清理仍待 Q01。未运行任何 RL 训练，真实参考数据库覆盖为 0。

2026-10-22 14:06 CST — S01 保留 WIP 再验：先检查 diff 并读取指定配置/文档，重跑 `python3 scripts/accept_phase.py S01` 退出 0；12 单元、8 全新目录集成全部通过、0 skip，desktop 真实无头渲染/点击/隔离断言通过，3/3 stage。证据 `artifacts/S01/runs/20261022T060641296645Z/`、`artifacts/acceptance/S01.json`；已查看本轮截图。既有来源/发行许可限制保留，未实现未来阶段。未修改调度状态、创建 Git 提交或改动 HEAD；正式完成由调度器决定。

> 当前状态（2026-10-22，S01 网络恢复续做）：S00 既有完成记录保留；S01 实现和验收材料就绪，真实声明测试退出 0：12/12 单元、8/8 全新目录集成、desktop 渲染通过，整体 3/3 stage、0 skip。正式阶段完成和 Git 保存由调度器决定；未执行或声明后续阶段完成。

2026-10-22：已完成需求基线、整体架构、开源研究、评估方法、数据契约和阶段队列设计。产品功能尚未实现，不标记任何开发阶段完成。

已存在：bootstrap 调度器、Git 仓库和 6 小时 systemd timer。历史轻量探测曾验证 Sol Medium/Astra xHigh 可通过 ChatGPT CLI 返回响应，不能据此宣称功能完成。

下一任务：S00，由 Sol High 加固调度器；随后按依赖图和额度逐阶段执行。当前架构聊天在启动交接后结束，不直接实现产品功能。

已知约束：GPU 驱动不可用；需要独立开发 Python 3.12/Node 工具链；用户未提供自己的机器人文件，因此初始验收用公开合法参考模型与自制变体，不能声称已评估用户真实机器人。

各阶段完成后追加摘要、测试结果、产物路径、剩余问题及下一任务。机器状态以 `.scheduler/state.json` 和完成 commit 为准；本文件不替代自动验收。

## 2026-10-22 — S00 实现与本地验收，真实验收受阻

已替换 bootstrap 为有界、ChatGPT only 的调度实现：模型/额度协议预检、完整依赖图、结构化结果和非空测试 gate、信号/进程组清理、证据日志、WIP/checkpoint 与 Git journal/trailer 恢复。50 个阶段及原有任务级别、依赖和 gate 保留，仅追加 S00 真实验收门禁；未实现未来产品功能。

实际本地故障测试：48 项通过，0 skip；包括真实子进程/数值断言/Git 事务，见 `artifacts/S00/unit-report.json` 与逐例压缩证据。配置图验证通过。真实 CLI 小任务在临时仓库尝试，model/list 成功，但 account/read 的 workspace routing discovery 失败，严格预检停机，未执行真实模型开发闭环。timer 部署因只读用户目录失败，短 timer 触发因 systemd 总线权限被拒绝，均未冒充通过。

验收文档：`docs/acceptance/S00.md`。S00 附加 gate 会因真实 CLI/timer 未通过而返回非零，**S00 保持未完成**；下一任务仍为补齐 S00 的真实验收。项目 `.scheduler/state.json` 未改，项目 Git HEAD 未改、未 commit/push。剩余风险包括同 UID 并发编辑识别、checkpoint 硬崩溃人工恢复、CLI 版本兼容和日志容量管理，详见验收记录。已有 6 小时 timer 配置保留；修订后的 service 尚未部署。

## 2026-10-22 — S00 复核修正，真实验收仍阻塞

本轮修复隔离登录目录写出项目的问题，改用工作区临时目录；故障测试统一使用自制身份，归档排除登录目录/软链接。补充锁内重新读状态、预检 RPC 429 立即共享退避、gate 后保护输入校验、原始测试日志证据哈希，以及已安装 timer/service 比对。真实烟测的后续独立临时仓库改放项目内部，避免当前 CLI 拒绝 /tmp helper；没有激活任何 API key 或自定义付费后端。

实际最终本地测试 **54 项通过、0 skip**，包含真实数值/子进程/Git/恢复断言；另以实际 systemd calendar 解析断言三个六小时间隔均为 21600 秒。50 阶段图验证通过，完整后续计划未改。本轮失败迭代和修正记录保留；中间两份跟随登录链接的本地归档已删除，最终归档无 auth.json 条目。

真实 CLI 本轮仅尝试一次小任务：initialize/model/list 成功，account/read 仍返回 workspace routing discovery failed，未进入 exec，不能视为真实开发闭环通过。用户 systemd 总线仍拒绝访问，且只读比对显示部署 unit 与源码不一致，未部署或验证触发。附加 gate 实际退出 1（本地通过、live/timer 未通过）；项目 dry-run 因外层调度器持锁实际退出 3。**S00 仍未完成，下一任务仍是 S00**，没有将未来阶段标记完成。

验收及继续入口：`docs/acceptance/S00.md`、`artifacts/acceptance/S00.json`。项目 state 与 HEAD 的前后哈希另存 `artifacts/S00/project-invariants.json`；本轮未编辑 state、未创建项目 Git 提交。需要在可用的既有 ChatGPT 路由和用户 systemd 权限环境补齐真实烟测/部署，然后由调度器验收决定完成。


## 2026-10-22 — 当前 Codex 会话接手 S00（timer 已按用户要求暂停）

自动 `urdftools-dev.timer` 已执行 `disable --now`，确认 `ActiveState=inactive`、`UnitFileState=disabled`、无下次触发；service 主进程为 0（unit 保留之前 failed 状态）。没有运行自动 scheduler/CLI 轮次。当前 Codex 会话只读执行 `scheduler.py doctor` 成功：`auth=chatgpt`，额度 `limitId=codex`（Plus），primary 19%/300 分钟，secondary 83%/10080 分钟；这明确是 Codex 使用桶，不是 ChatGPT Chat 消息额度。随后重跑本地 S00 检查：54 tests、0 failures/errors/skips；`scheduler.py validate`：50 阶段全部配置有效。`completed=[]`、S00 `retry_requested`，阶段仍未验收完成。

未启动真实 CLI 小任务，因为用户要求停掉自动 CLI 并在当前 Codex 会话续做；S00 的真实 CLI 开发闭环仍需之后单独验收。timer 也刻意保持 disabled，因此 systemd 的已部署 unit 匹配及实际调度触发验收仍未完成。续做证据详见 `docs/acceptance/S00.md`。

当前会话补充：在不启动产品 timer/service 的情况下，独立两秒 `systemd-run --user` probe 实际触发并写出 token 标记，耗时 2.076 秒。综合 verifier 仍为 blocked，因为永久 timer 按要求保持 disabled，且已安装 unit 与源码 hash 不匹配；报告在 `artifacts/S00/manual-paused-timer-probe/report.json`。


## 2026-10-22 — S00 真实 CLI 烟测通过，准备自动部署

当前会话从项目内独立临时仓库运行 `scripts/scheduler_live_smoke.py`。首次预检在 `account/rateLimits/read` 被拒并安全进入 `quota_wait`，未执行模型；只读诊断随后成功，第二次有界运行（63.721 秒）以 Sol Medium 完成数值小任务，四项数值断言通过，由隔离调度器创建一次 Git 完成提交，重复运行无重复提交。报告为 `artifacts/S00/live-smoke/report.json`。S00 主项目仍未完成，须通过安装 timer 和正式 S00 gate。

2026-10-22 11:29：`install-timer.sh` 已将源码 unit 部署到用户 systemd，六小时 timer active/enabled，下次触发为当日 12:00 CST。实际两秒 transient timer probe 于 2.135 秒触发，部署 hash 完全匹配。S00 三项机器 gate 全部通过（3/3）；主项目状态仍是 S00 `retry_requested`，待调度器正式执行并保存阶段完成事务。

## 2026-10-22 11:35 — S00 当前源码复核，修复 Git 证据重试及结构化 429

复现并修复两个缺口：Git ref-lock 提交失败后的重试原会重新接受被改写的验收日志，现于 gate 后在 journal 固定证据哈希，恢复不符即停止且不再调用模型；嵌套 HTTP 429/401 和大小写变体错误枚举现正确识别，明确 429 不再作为 unknown 放行 exec。新增 5 项回归，先失败日志保留；旧 pending journal 缺少证据哈希须人工核对，已有 Git trailer 哈希格式保持兼容。

实际完整测试 **59 项通过，0 failures/errors/skips**；50 阶段配置图及全部原计划比较通过，六小时 calendar 三个间隔均为 21600 秒。没有缩减或执行未来阶段。当前源码真实 CLI 烟测只尝试一次，3.853 秒后因 account/read 的 `workspace routing discovery failed` 记录 auth_required，内层退出 75，未到 exec，不能沿用旧源码的成功来宣告完成。systemd 本轮受沙箱总线权限拒绝，已安装 unit 哈希仍匹配，永久 timer 未改；11:29 的同版本 timer 真实触发记录保留。

S00 综合 gate 退出 1（local/历史同版本 timer 通过、当前源码 live 阻塞，2/3）。**S00 未完成，下一任务仍为 S00 真实复验**。项目 `.scheduler/state.json`、Git HEAD、完整 phase 图均未改，未创建项目 Git commit/push。临时 fixture 仓库中的 Git 操作仅用于实际事务验收。详见 `docs/acceptance/S00.md` 最新复核、`artifacts/acceptance/S00.json`、`artifacts/S00/review-20261022/`。


## 2026-10-22 — 30 秒启动验证与四小时长期调度

用户指定的 30 秒临时 systemd timer 实际触发，`urdftools-dev.service` 于 11:31:49 CST 启动 S00，当前 GNOME 系统终端持续显示真实状态和 CLI 日志。该轮 S00 补强 Git 恢复证据校验及嵌套 HTTP 429/401 识别，本地 59 项测试通过；由于模型沙箱内的登录路由/systemd 总线受限，阶段返回 blocked_input，改动由调度器保存为 checkpoint。操作会话已用调度器恢复方法取回 checkpoint，按用户最新指令改为四小时 timer 和 14400 秒额度退避，实际部署与短探针通过。针对最新源码重新运行 59 项测试、Sol Medium 真实 CLI 数值任务、Git 提交/去重和 timer 验证，`check_s00_acceptance.py` **3/3 通过**。S00 主项目状态仍为 blocked_input，待调度器正式重试与提交；没有提前标记完成。

## 2026-10-22 11:46 — S00 保留 WIP 续接验收就绪

先检查 diff，保留既有调度实现与四小时 timer。本轮实际运行声明测试：59/59 通过、0 skip；50 阶段图有效；综合 gate 3/3，全部退出 0。独立 fixture 的数值重算 4/4，通过 24 项只读断言核对宿主源码/测试/部署哈希、真实 CLI 的 ChatGPT/Sol Medium 请求、Git 父提交及证据 trailer、重复运行 no-op、timer 原始进程和 2.113 秒触发标记。宿主报告均与当前文件匹配，按任务授权复用；未另启模型或 systemd 探针。

更新验收首页与机器摘要，保留旧 blocked 摘要及失败记录。证据见 `artifacts/S00/resume-review-20261022/`、`docs/acceptance/S00.md`、`artifacts/acceptance/S00.json`。源码/测试/timer/verifier 未再修改；项目 HEAD、state 及 scheduler.json 前后哈希相同，未创建项目提交，未来 49 阶段与基线完全一致。S00 实现及验收材料已就绪，正式阶段完成和提交仍交外层调度器决定。旧 pending journal、同 UID 并发编辑、硬崩溃、协议兼容及日志容量风险继续如实保留。


2026-10-22 11:52 运维修订：systemd 用户 service 现以 `SuccessExitStatus=75` 识别调度器主动的额度/认证/模型等待，调度状态仍保留 `quota_wait` 与最早可重试时间；其它非零退出仍为失败。四小时 timer 保持 active/enabled，安装 unit 与源码匹配，独立短探针 2.131 秒实际触发，S00 当前验收门禁仍为 3/3。


## 2026-10-22 — S01 独立工具链与应用骨架，整体验收阻塞

仅处理 S01。新增独立 Python 3.12.14 / Node 24.19.0 / npm 10.9.9 引导、Python SHA256 完整锁、24 包 Linux npm integrity 锁、安装后的 CLI、FastAPI 回环服务骨架、React/TypeScript 中文空壳及待运行 Electron 主进程/preload。新增真实多阶段验收器，零发现/全 skip/失败明确非零，未知未来阶段拒绝运行；记录 238 条开发第三方组件及可取得的原始许可。

阶段声明命令 `python3 scripts/accept_phase.py S01` 实际退出 **1**：单元 **9/9 通过、0 skip**；全新含空格目录集成 **6 项发现、4 通过、2 失败、0 skip**。独立安装、CLI/prefix/pip check、生产构建及同进程 React SSR 的 **2 个真实用例**通过；真实服务 socket 和 Vite preview 启动被沙箱 EPERM 拒绝。Electron gate 退出 2，因固定版本 lock/Linux runtime 未在离线缓存中，未启动 GUI。最终多阶段 gate **1/3 通过**，不以构建或 SSR 代替 GUI。50 阶段配置 validate 通过仅代表配置有效。

证据：`docs/acceptance/S01.md`、`docs/TOOLCHAIN.md`、`artifacts/acceptance/S01.json`、`artifacts/S01/runs/`、`artifacts/S01/clean-install-commands.json`、`third_party/manifest.json`。保留复制 symlink、缺 Node lock、Node 测试隔离未登记用例及账本 duplicate key 的失败迭代与修复记录；最终计数强制核对实际测试数量。运行时 seed 已复制到本项目，不依赖 Codex 缓存长期存在，但上游完整构建 provenance/Node combined notice/部分 bundled 组件许可尚待补齐，不能作为发行包。Three.js viewer、CAD/GPU、训练和其它后续阶段未实现或验收。

本轮未编辑 `.scheduler/state.json`，未创建 Git commit/push、未变更阶段图/后续任务要求、未启用模型或付费 API、未修改系统 Python/驱动、未上传 CAD/私有仓库。下一步仍为补齐 S01：在允许回环 socket 的环境复验服务/preview，取得并审查 Electron lock/runtime/notices，执行真实桌面 smoke，再由调度器决定阶段完成。


## 2026-10-22 — S01 保留 WIP 续接复核

先检查 Git diff，并读取任务、scheduler.json、需求、架构、调度授权与既有验收记录。仅续做 S01：引导子进程改用环境白名单，屏蔽继承的 Python/Node 注入、包索引配置及凭据，并隔离 npm 用户/全局配置；文档使用 `python3 -E`，使引导解释器本身也不继承 Python 环境变量。全新含空格目录实际在无效 PYTHONHOME/PYTHONPATH/NODE_OPTIONS/PIP_TARGET/npm 配置输入下完成安装、CLI/pip check、生产构建和两个 SSR 用例。

验收超时现在终止整个 stage 进程组，保留超时前输出；真实父子进程延迟写入回归验证没有留下继续运行的子进程。修正 fixture 初始化错误导致负数 passed 的计数问题，改为统计实际成功用例。首轮新增测试导入和 npm 配置路径失败均保留在 `artifacts/S01/resume-declared-first.log`，随后修正并重跑。

声明命令 `python3 scripts/accept_phase.py S01` 最终退出 1：单元 **12/12 通过**；集成 **6 发现、4 通过、2 失败**；均 0 skip。两个失败仍为 socket EPERM；Electron gate 退出 2，固定依赖 lock/runtime 未取得。独立探测再次确认 registry DNS 失败、回环 socket 创建 EPERM。整体 gate **1/3**，**S01 未完成**。`scheduler.py validate` 50 节点有效仅为配置检查。最终日志 `artifacts/S01/resume-declared-final.log`，报告 `artifacts/acceptance/S01.json`，完整来源/剩余许可与运行时 provenance 风险仍见 `docs/acceptance/S01.md`。未改 state、scheduler.json、任务要求或 HEAD；未创建提交、调用其它模型、执行后续阶段。


## 2026-10-22 — S01 网络恢复、完整真实验收通过

先检查保留 diff 并读取阶段/设计授权，仅处理 S01。重新实测服务与 Vite preview 回环成功；新增 desktop 官方 npm lock（70 个固定 integrity 包）、Electron 39.2.7 Linux runtime lock、显式离线安装器及真实 headless/offscreen 渲染验收。GitHub 资产直链 TLS 失败后，公开镜像归档与官方发布 API digest/SHASUMS 双重比对通过，74 文件安装校验；补齐 Electron/Chromium 和 Node combined notices，账本 309 个开发组件。未继承 registry 凭据/付费 API，未关闭 Chromium sandbox。

真实渲染暴露 React 异步挂载时序问题，修为有界等待，实际点击工作区、隔离/preload/sandbox 断言和 1200×800 PNG 均通过。全新含空格目录离线安装包含桌面 runtime，另实测缺失/损坏归档在安装前明确失败。最终 `python3 scripts/accept_phase.py S01` 退出 0：12/12 单元、8/8 集成、0 skip，desktop 独立通过，整体 3/3 stage；SSR 额外两个真实用例通过。命令、输入、输出、失败迭代及截图见 `docs/acceptance/S01.md`、`artifacts/S01/network-declared-final.log`、`artifacts/acceptance/S01.json`、`artifacts/S01/clean-desktop/`。

S01 材料交调度器决定正式完成/提交。本轮没有改 state、scheduler.json、项目 HEAD 或任务图，没有 Git commit/push、子模型、未来阶段实现。开发 seed 的完整上游构建 provenance、keyv 缺许可全文及部分 bundled 组件发行审查、真实 GNOME/GPU/打包验收仍有明确限制；不把它们宣称完成，详见验收记录。

## 2026-10-22 用户范围修订与恢复

产品采用外部训练结果库与证据分析架构，详见 docs/RESULTS_DATABASE.md、docs/TASKS.md；不实现 RL 训练器。普通/复杂/关键分别 Sol Low/Medium/High，Astra 当前不启用。S01 上次真实 gate 通过，但 Chromium 许可证触发大文件检查而未提交；已逐字节核验官方运行时文件并精确放行。本次保留原始成果，交调度器真实重验与提交，不能将该运维修订当 S01 已完成。小时 timer 和防并发锁保留。

## 2026-10-22 — S02 领域模型与一致契约，验收材料就绪

仅处理 S02。实现 Pydantic 冻结 RobotDocument/快照/来源证据与显式 SI/frame、树/引用校验、
规范 JSON+资产 hash、文档/快照保存读取、v1 备份迁移、共享 UI/agent 预览/确认/冲突校验和
undo/redo；生成 JSON Schema 与只读 TypeScript 类型，不新增第三方依赖。

实际 `python3 scripts/accept_phase.py S02` 退出 0：26/26 领域/契约测试、0 skip，
独立文档保存流程通过，2/2 stage；原有验收器/工具链 12/12 回归也通过。
双连杆 2 link/1 joint（3.25 kg）、四足树 9 link/8 joint（8.875 kg）往返完整数值与 hash 一致；
拒绝非法图、NaN/Infinity、单位/frame/引用错误，验证旧 schema 原字节备份及冲突事务无修改。
真实 tsc 编译实际夹具及负向类型断言通过；快照、迁移备份、编辑 diff/事务与数值摘要保留。
首次因 S01 非 editable 安装缺新模块导致的导入失败原始日志保留，已修正验收源码路径。

证据：`docs/acceptance/S02.md`、`artifacts/acceptance/S02.json`、`artifacts/S02/runs/`、
`artifacts/S02/workflows/`、`tests/fixtures/S02/`；字段与接口约束见 `docs/CONTRACTS.md`。
全部输入为原创 CC0 synthetic_fixture，真实参考成绩覆盖 0；不实现训练器。
限制包括 JSON 而非 URDF 导入、内存历史非持久多进程事务、文件读取并发竞态、物理合理性未验，
均已明确记录。未修改 state、scheduler.json 或创建 Git 提交；正式阶段完成由调度器决定。
未执行或声明后续阶段完成，S03 及其它后续需求完整保留。

2026-10-22 S02 保留 WIP 续接复核：先检查 diff 并读取指定文档。新增真实回归复现并修复
非布尔确认误提交、超大有限轴数值平方溢出；失败日志 `artifacts/S02/review-first.log` 保留。
声明命令 `python3 scripts/accept_phase.py S02` 退出 0，28/28 测试、0 skip、2/2 stage，
文档与快照数值往返、迁移备份、事务工作流及真实 tsc 均通过；原验收器/工具链 12/12 回归通过。
详见 `docs/acceptance/S02.md`、`artifacts/acceptance/S02.json`。本轮未改 state、HEAD、
scheduler.json 或创建提交；配置中既有阈值 diff 原样保留。仅 S02 材料就绪，正式完成由调度器决定，
未执行或宣称后续阶段完成；既有 JSON/内存事务/文件竞态/物理验证限制仍保留。
## 2026-10-23 — A00 受约束 Agent 工具层

已完成结构化 CAD 建议的白名单校验、隔离预览与人工确认应用；接入当前 ChatGPT 登录的 Codex CLI 和仅回环本地模型端点。用户明确授权仅发送 CAD 配方与建模指令，未发送本地 STEP/FCStd 或密钥，未启用额外付费 API。真实 CLI 对原创测试配方建议 Body 宽度 20→30 mm，CAD 质量 0.0027→0.00405 kg，确认前版本指针字节不变，确认后版本 1→2。正式 A00 门禁 2/2 通过、0 skip；证据见 `docs/acceptance/A00.md` 与 `artifacts/acceptance/A00.json`。本地模型仅经回环测试服务器验证；A01 界面集成和 A02 MCP 仍待开发。
## 2026-10-23 — A01 Agent 辅助建模

完成 Electron 建模工作台的自然语言建议、参数/质量差异与完整配方预览、拒绝、人工确认应用及复制配方后微调。真实 ChatGPT Codex 对原创双连杆只修改 Arm 宽度；拒绝不改工程，接受后版本 1→2，URDF 独立校验 2 Link/1 Joint，撤销并重建为版本 3。正式 `.venv/bin/python scripts/accept_phase.py A01` 2/2 门禁通过、0 skip；TypeScript/Vite 构建通过。证据见 `docs/acceptance/A01.md`、`artifacts/acceptance/A01.json`、`artifacts/A01/desktop/`。训练性能仍未评估，A02 CLI/MCP 接口尚待开发。
## 2026-10-23 — A02 CLI 与 MCP 受限工具接口

完成共享的 CLI JSON/MCP stdio 工具信封，开放导入、CAD 隔离预览、STEP 转换检查、URDF ZIP MuJoCo 验证四项能力。相对路径、符号链接逃逸和内部存储目录逃逸被拒绝；模型接口没有直接应用工具。正式 `.venv/bin/python scripts/accept_phase.py A02` 1/1 门禁通过、0 skip，真实多模型 ZIP、双零件 STEP、CAD 质量变化与 2 Link/1 Joint 物理包均实际验证；CLI/MCP 成功与错误信封一致。证据见 `docs/acceptance/A02.md`、`artifacts/acceptance/A02.json`；用法见 `docs/AGENT_TOOLS.md`。目前 MCP 只支持 2025-06-18 初始化协议，评估工具仅验证物理包，训练结果比较仍在后续阶段。

## 2026-10-24 — 查看与 URDF 建模合并

依用户新要求，顶部「查看」「建模」合并为「URDF 工作区」。保留原查看器和各浮动面板，新增按钮打开 URDF 代码、CAD 模块库和 Agent CAD 面板。关节/结构选择可定位代码；编辑、删子树、会话内撤销重做与资源包导出经本地校验。CAD 模块库持久保存实际 STEP→STL 或 STL/OBJ，支持拖入、点击两个连接位置和确认固定/连续旋转关节；保留 Agent 的双模式建议预览和确认后入库。源模型不被覆盖。

实际 TypeScript/Vite 构建、React 2/2、Python STEP 往返 3/3、隔离 Electron 拖放和连接及 Agent CAD 入库、导出 ZIP 重新导入均通过。详见 `docs/acceptance/URDF_WORKBENCH.md` 和 `artifacts/URDF_WORKBENCH_2026-10-24/`。本轮没有调用真实 AI 建模回复，也没有对用户真机模型逐面手动点选；CAD 新模块仅含视觉网格，没有凭几何推断动力学参数。原复杂建模阶段验收需按新交互重写，未宣称重新通过。旧 WIP 改动保留，未改 `.scheduler/state.json`，未提交包含历史 WIP 的 Git 版本。

## 2026-10-24 — 重力轨迹、关节限位与窗口缩放

重力模拟现在读取当前活动关节姿态，返回约 30 帧/秒的轨迹，查看器以 ¼ 倍速插值播放下落过程；关闭重力时恢复原姿态。关节面板增加逐关节「应用 URDF 限位」，关闭后同时放开交互预览和 MuJoCo 关节约束；该开关不改写 URDF。所有浮动面板新增四边和四角的缩放手柄。

TypeScript/Vite 构建通过；双连杆示例的三个仿真工况回归通过，确认起始关节值进入首帧且关闭限位会改变最终角度；A1 用户模型隔离 Electron 回归通过，确认慢速播放状态、最终 12 关节同步和八方向缩放手柄。保留既有未提交 WIP。

## 2026-10-24 — 重力落地防穿透与抑制反弹

根据用户反馈，重力预览改为用 MuJoCo 碰撞体到地面的实际距离初始化高度，并在每个物理步将超过 0.5 mm 的软接触穿透投影回地面；接触后耗散速度，降低无控制器落地的反弹。播放时对视觉网格相对碰撞体的地面偏差做仅用于显示的贴地校正，并在结果栏报告较明显的偏差。活动关节在初始加载时按启用的 URDF 限位取合法值，避免仿真首帧因非法默认角度突变。

TypeScript/Vite 构建、双连杆和 A1 仿真回归 2/2 通过。A1 仿真记录的最大碰撞体入地小于 0.5 mm，整段向上位移约 7 mm；隔离 Electron A1 回归通过，最终视觉网格最低点在地面上方 1 mm。该 A1 的视觉网格与碰撞体最大显示偏差约 42 mm，界面已提示。无驱动 A1 10 秒后仍有缓慢关节运动，不能声称达到动力学平衡或保持站立；播放器结束后静态展示最后姿态。历史 WIP 保留，未提交。

## 2026-10-24 — 重力预览起始抬高、反弹与悬空再修正

按用户截图复核，前一版仍把碰撞体人为抬高 40 mm 后再落下，显示层也只向上纠正穿地而不向下纠正悬空。本轮将 MuJoCo 首帧直接置于碰撞接触高度（约 0.1 mm 间隙），接触后移除向上的基座速度；查看器每帧按视觉网格最低点双向贴地，且仅在播放过程中平滑跟随视角，避免模型下沉后移出画面。源 URDF 保持不变，仍将显著的显示校正量告知用户。

TypeScript/Vite 构建、双连杆与 A1 物理回归 2/2、A1 隔离 Electron 全程播放均通过。桌面回归新增点击前/播放首帧根部高度差不超过 10 mm、首帧和最终视觉最低点接近 z=0 的检查；最终视觉最低点 1 mm。A1 无驱动关节在 10 秒后仍可能缓慢运动，不能将贴地预览误称为有控制器的稳定站立。

## 2026-10-24 — A1 落地后脚部悬空修复

按用户侧视截图复核，落地后的最低视觉网格实际是后腿大腿，不是足端；按整机网格最低点对齐地面会把四只脚抬高约 45 mm。重力播放现优先以足端视觉几何对齐 z=0，其他没有足端的模型沿用原回退逻辑；清除了临时诊断输出，源 URDF 与 MuJoCo 碰撞计算未改。TypeScript/Vite 构建、MuJoCo 双模型回归 2/2、真实 Electron A1 播放通过，足端最终最低点 z=0.001 m，物理接触 1 处。A1 大腿视觉几何与碰撞体仍不吻合，足端贴地后其一部分可能位于地面以下；此修复只处理用户报告的可见悬空。

## 2026-10-24 — mybot_v3 预览材质、结构角度单位及重力速度

按用户提供的同模型对照图，重力轨迹播放改为 2/3 倍速。结构栏新增弧度/角度切换，节点与选中关节读数同步，移动关节始终显示米；切换只改变读数，不改 URDF 或关节姿态。查看器将原先统一的无光照白色材质替换为保留源颜色/贴图的受光材质；未贴图的近白 STL 采用中性灰预览，调整环境光、主灯与阴影，并修复异步网格加载后漏设投影属性。

TypeScript/Vite 构建通过；真实 Electron 导入用户 mybot_v3（18 Link/17 Joint、17 网格文件、18 个受光视觉网格）通过，单位切换保持关节值和源物理字段不变；无遮挡截图 `artifacts/S06/desktop/mybot-v3-lighting-2026-10-24.png` 可见灰色面片明暗及地面阴影。A1 桌面重力回归通过，显示 2/3 倍速，末帧足端距地 1 mm、1 处物理接触。mybot_v3 本身没有贴图文件；这里呈现的表面细节来自 STL 几何和光照，不是新增纹理数据。

## 2026-10-24 — 多 URDF 对比与显示选项

显示与姿态栏新增惯量蓝色透明框、已知质心、阴影开关，统一作用于并排查看的所有 URDF；惯量框由 URDF 质量及惯量对角项近似计算，不表示原始碰撞体或 CAD 精确形状。一次拖入多个 URDF 后，对比查看栏可指定当前编辑/关节操作对象，其余模型仍显示在同一网格场景；重力预览为每个模型分别计算轨迹并同步播放，关闭后恢复各自姿态。mybot_v3 + 两份 A1 的真实 Electron 拖入、切换、全局显示与三模型重力回归通过；TypeScript/Vite 构建、MuJoCo 物理回归 2/2 和 `git diff --check` 通过。界面证据：`artifacts/S06/desktop/urdf-compare-ui-final-2026-10-24.png`。
## 2026-10-24 — STEP 真实网格与交互式 Link 分组修正

针对用户 `Quadruped Robot.STEP` 的“彩色方盒而非 CAD 装配”反馈，新增逐零件 STEP 三角化工作流与受限本地网格协议；转换工作区现用原始零件三角面显示，支持 OrbitControls 三维旋转、点击黑色多选/再次取消、隐藏和恢复零件。Link 面板改为右侧：先建立固定名称 `base_link`，其余 Link 自定义名称，并为每个非基座 Link 选择父 Link；未分组零件仍可通过列表选择。完整分组后才能设置关节。用户真实文件已生成 43 个 STL、约 7.7 万个三角面、总计 3.85 MB。C00/C03 Python 测试各 4 项、TypeScript 和 Node 语法检查通过；前端已在 `/tmp/urdf-cad-build` 成功构建。项目内正式构建因自动审批服务返回 403 未执行，Electron 头less 烟测在当前沙箱因 Chromium sandbox host 权限错误未能启动，因此本轮不得声称真实桌面交互已验收。恢复审批/桌面运行条件后应重建 `dist/web` 并重跑 C03 桌面 gate。
## 2026-10-24 — CAD 转换视图改为拖动机器人

根据用户澄清，CAD 零件工作区移除地面网格与 OrbitControls 视角旋转。左键拖动现在绕装配中心旋转机器人模型，单击仍点选零件，滚轮只调整距离；关节连接点在旋转后的模型上点击时逆变换回原始 CAD 坐标。已更新项目内 `dist/web`。真实 Electron C03 烟测重新通过：脚本拖动后模型四元数变化而相机位置保持不变，零件点选、关节轴向调整和 2 Link/1 Joint URDF/ROS ZIP 导出仍通过。见 `artifacts/C03/desktop/report.json`。

## 2026-10-25 — CAD 转换 Joint 与 Link 同步建立

子 Link 建立时立即按父子关系生成 `<子Link>_joint`，Link 树可直接点选 Joint 打开设置栏。新 Joint 先比较父子 Link 的圆柱面轴线；没有匹配时保留未解析位置，仍待人工确认。当前轴线以红环和蓝箭头标注；Joint 栏提供命名、父子 Link、类型、角度/位移限位、自动识别、两点设轴、反向、手工坐标与试转。TypeScript/Vite、几何推断测试、真实 Electron C03 双零件导入—点选 Joint—试转—ZIP 导出/MuJoCo 校验通过。见 `docs/acceptance/C03.md` 与 `artifacts/C03/desktop/report.json`。43 零件用户 CAD 的每个实际轴线仍需人工逐项核对。

## 2026-10-25 — CAD 转换 Link 树与多候选轴交互

根据用户截图，Link 栏改为结构树与逐项可见性控制，中央创建弹窗指定 Link 名称和父 Link，树中点击 Joint 才打开下方 Joint 设置栏；双击可重命名。模型支持右键平移。轴自动识别改成父子零件圆柱面对轴，按零件配对每对最多一轴；“显示全部轴”呈红色透明候选环，悬停蓝色并显示方向箭头，点击后才应用。缺少共同几何证据时不假称已识别轴，改用两点或精确参数。双零件 Electron C03 完整导出回归通过；用户真实 43 零件 STEP 中的 `shenti` ↔ `fake_servo_2_1` 配对识别 1 轴，桌面悬停与选定烟测通过。证据见 `docs/acceptance/C03.md`、`artifacts/C03/desktop/real-axis-report.json`。所有实际机械轴仍需用户逐项确认。
最终 C03 阶段门禁 4/4 通过、0 failed、0 skipped；生产构建和轴候选 3 项测试通过。

## 2026-10-25 — URDF 工作区选中旋转关节的轴向标记

查看器选中 revolute/continuous 关节时，在实际关节原点绘制红色圆环，并以蓝色箭头指向 URDF 轴的正方向。标记按关节当前世界姿态逐帧更新；切换到 Link 或非旋转关节时隐藏。TypeScript/Vite 构建及 Go2、G1 真实 Electron S06 回归通过，验证轴方向为单位向量、关节调节后仍存在、切换 Link 后消失。截图见 `artifacts/S06/desktop/go2-selected-axis.png` 与 `artifacts/S06/desktop/g1-selected-axis.png`。

## 2026-10-25 — 双工作区交互栏停靠与四分之一屏放大

URDF 工作区导入模型后，文件、显示、代码、对比、CAD 库与 Agent 栏按顺序停靠左侧；结构、关节、物理与测量栏停靠右侧。CAD 转换完成导入后，Link 与试转栏在左、选中的 Joint 设置栏在右，保留从 Link 树选 Joint 才打开设置的交互。两侧栏可独立滚动，初始窗口不互相覆盖；拖动可脱离侧栏，八方向拉伸保持可用。各栏的放大菜单可选左侧、右侧或底部四分之一屏，放大时允许覆盖其他栏，还原后回到原位置。生产构建和 Go2、G1 真实 Electron S06 回归通过，回归检查初始顺序、无重叠、三种放大尺寸与还原；截图见 `artifacts/S06/desktop/{go2,g1}-docked-layout.png`。CAD 桌面流程已截图复核 Link/Joint/试转栏初始位置，完整 C03 门禁结果见 `docs/acceptance/C03.md`。

## 2026-10-27 — Electron 页面缩放快捷键可恢复

接管 Electron 默认的 `Ctrl+-` / `Ctrl++` 页面缩放快捷键，按相同的半级缩放增减，避免键盘布局差异导致减小后无法用加号恢复；`Ctrl+0` 恢复 100%。应用启动时也将页面缩放归零，防止 Electron 上次保存的缩放比例让所有面板一开始就过小。生产构建与桌面主进程语法检查通过；当前没有交互式按键回归记录。

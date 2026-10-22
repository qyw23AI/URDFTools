# URDFTools 项目进度

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

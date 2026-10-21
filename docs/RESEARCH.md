# 开源检索与技术取舍

检索日期：2026-10-22。下列判断来自项目作者仓库/文档；“可选”或“待验证”不表示已经安装、运行或通过验收。实施阶段须固定提交、复核具体代码/资产许可、运行自己的夹具再采用。默认通过依赖包使用成熟库；需要改动源码时以保留来源的 vendor/fork 适配，记录补丁与 notices。

## 用户提供的参考

| 参考 | 已核实的能力与决定 |
|---|---|
| [gkjohnson 示例](https://gkjohnson.github.io/urdf-loaders/javascript/example/bundle/) / [源码](https://github.com/gkjohnson/urdf-loaders) | 页面具有文件夹拖放、关节、碰撞和视角控制。JavaScript loader 提供 packages 映射与自定义 mesh loader；Apache-2.0。采用为主显示加载器，复用前保留 Caltech/JPL notices。 |
| [Robotsfan Viewer](https://viewer.robotsfan.com/) / [fan-ziqi/robot_viewer](https://github.com/fan-ziqi/robot_viewer) | 已找到实际公开源码（下划线仓库名），README 覆盖 URDF/Xacro/MJCF、部分 USD、惯量显示、测量、代码编辑、仿真；Apache-2.0。提取合适的交互/解析适配，统一本项目数据模型，避免整站嵌入后双重状态。 |
| [StackForce CAD2URDF](https://cad2urdf.stackforce.cc/upload) | 本次页面抓取不可访问，未找到能明确归属该服务的公开许可源码。因此只记录用户给定的转换流程参考，不声称已检查其实现或复制代码。采用下面可验证的开源替代。 |

## CAD、数据与建模

| 项目 | 用途、许可线索与取舍 |
|---|---|
| [step2urdf](https://github.com/edsamsankey/step2urdf) | MIT；README 描述 STEP 装配、link 分组、关节建议、CAD 质量属性、可保存配置和 roundtrip 测试。优先做适配验证，重点独立测试单位、材料和惯量 frame；不能把其自动关节推断直接当作机构真值。 |
| [RobotCAD](https://github.com/uid17/freecad.robotcad) | FreeCAD 机器人工作台，关节/零件/惯量/碰撞和 ROS 导出；仓库元数据为 LGPL-2.1。作为可选外部 CAD 桥，发行时核实组件具体条款与所需运行时。 |
| [build123d](https://github.com/gumyr/build123d) | Apache-2.0，基于 OpenCascade 的参数化 BREP 建模；主建模内核，提供可复算参数操作与 STEP 输出。当前 README 支持 Python 3.11+，本项目选独立 3.12。 |
| [CadQuery](https://github.com/cadquery/cadquery) | Python 参数化 CAD 的备选生态；不同时维护两套主建模 DSL，保留适配可能。具体 OCP/库许可在版本锁定时检查。 |
| [onshape-to-robot](https://github.com/Rhoban/onshape-to-robot) | MIT；通过 Onshape API 读取装配并导出 URDF/SDF/MuJoCo。依赖外部账户，列可选连接器；默认离线功能不依赖它。 |
| [SolidWorks exporter](https://github.com/ros/solidworks_urdf_exporter) | 经典 SolidWorks 导出工作流参考；Windows/CAD 侧工具，面向机械组给说明。 |
| [sw2robot](https://github.com/jsk-ros-pkg/solidworks_urdf_exporter2) | README 标 Apache-2.0；extract 需要 Windows + SolidWorks，graph 编辑/构建/导出可跨平台。适配 graph 包，不能把其跨平台编辑宣传为 Ubuntu 原生读取 SLDASM。 |
| [yourdfpy](https://github.com/clemense/yourdfpy) | MIT；Python URDF 解析器，作为交叉解析/FK 依赖。不要无损保留能力超过实际实现。 |
| [CoACD](https://github.com/SarahWeiii/CoACD) | MIT；面向碰撞的凸分解。用于复杂碰撞代理，并记录精度/部件数/时间的取舍；不用于自动确定真实质量。 |

## 动力学、仿真、训练与参照资产

| 项目 | 决策 |
|---|---|
| [MuJoCo](https://github.com/google-deepmind/mujoco) | Apache-2.0；本地 CPU 物理基线。URDF/MJCF 编译差异须显式记录，禁用隐藏源模型错误的自动修补。 |
| [Pinocchio](https://github.com/stack-of-tasks/pinocchio) | BSD-2-Clause；FK/动力学/雅可比与解析导数的独立核验来源。 |
| [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) | 高质量 MJCF 候选库，模型子目录有各自许可；按模型固定 hash，不能套用一个统一许可。 |
| [Unitree ROS](https://github.com/unitreerobotics/unitree_ros) | 官方 URDF 来源候选，仓库元数据 BSD-3-Clause；资产及各目录继续核查。A1/Go2/G1/H1 版本与电机资料不能靠品牌名推定。 |
| [robot_descriptions.py](https://github.com/robot-descriptions/robot_descriptions.py) | Apache-2.0 的发现/加载包装；第一次加载可自动下载，产品需先显示网络/许可并固定内容，底层模型许可仍单独处理。 |
| [MuJoCo Playground](https://github.com/google-deepmind/mujoco_playground) | Apache-2.0；MJX/Warp 的四足、人形、操控训练环境。借鉴任务/配置和真实 baseline，核验与本项目协议一致性。 |
| [mjlab](https://github.com/mujocolab/mjlab) | Apache-2.0；MuJoCo-Warp 与 manager API。README 明确训练要求 NVIDIA GPU，因此只作为可选加速适配。 |
| [RSL-RL](https://github.com/leggedrobotics/rsl_rl) | 机器人 PPO/蒸馏训练库；用于加速适配。具体版本许可证需核对，不能依据 GitHub 的 NOASSERTION 判为无许可或直接分发。 |
| [Isaac Lab](https://github.com/isaac-sim/IsaacLab) | 可选导出/对照适配，依赖和硬件较重；发行时核查代码、资产和 Isaac Sim 的分别条款。当前不作为主应用前置。 |
| [Gymnasium](https://github.com/Farama-Foundation/Gymnasium) / [Stable-Baselines3](https://github.com/DLR-RM/stable-baselines3) | CPU 环境 API 与 PPO 候选；实施阶段锁版本和实测 save/resume、normalizer、RNG 恢复。 |

## 评估、设计优化与统计依据

- [rliable](https://github.com/google-research/rliable)：分层 bootstrap、IQM、performance profiles；用于体现跨 seed/任务波动，不能把相关 episode 当独立训练样本。
- [RoboGrammar](https://github.com/allanzhao/RoboGrammar)：图文法和地形相关机器人设计搜索的参考。启发受约束设计空间，不能直接迁移其指标为通用 URDF 质量标准。
- [RoboMorph 项目及论文](https://robomorph.github.io/)：LLM 提出设计，在控制评估/进化循环中验证；支持本项目“提建议→跑试验→回看证据”的研究路线，不构成商业机器人设计已验证的保证。
- [Drake RotationalInertia](https://drake.mit.edu/doxygen_cxx/classdrake_1_1multibody_1_1_rotational_inertia.html)：惯量的作用点、表达 frame、主惯量与物理有效性检查，转化为带解析夹具的规则。
- [Modern Robotics 质量矩阵](https://modernrobotics.northwestern.edu/nu-gm-book-resource/8-1-3-understanding-the-mass-matrix/)：姿态相关的质量矩阵与动力学解释。skills 引用方法和来源，不复制教材。
- [MuJoCo 建模](https://mujoco.readthedocs.io/en/stable/modeling.html) / [编译器参数](https://mujoco.readthedocs.io/en/stable/XMLreference.html#compiler)：转换、接触、惯量推断的实现核验依据。

结论：现有开源组件能覆盖相当部分查看、转换、建模与训练基础设施；未找到可直接替代本项目完整“URDF 设计质量→公平训练→机械反馈”模块的通用成品。该部分采用可测试规则、类型知识、对照实验、统计和受证据约束 agent 组合实现。

## Codex 执行依据

[非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode) 支持显式模型参数、结构化结果和脚本运行；[app-server](https://learn.chatgpt.com/docs/app-server) 文档列出 `model/list`、`account/read`、`account/rateLimits/read`。前一版只检测 CLI 错误，本次将额度预检和支持模型查询列入 S00，并要求用本机版本实测，失败时保留 unavailable 而不伪造百分比。[配置参考](https://learn.chatgpt.com/docs/config-file/config-reference) 包含强制 ChatGPT 登录方式；不得自动兑换额度重置或调用付费 API。

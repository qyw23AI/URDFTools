# MyHIMLoco / WMP 原始训练目录导入

本说明依据本机 `/home/qyw/MyHIMLoco` 与 `/home/qyw/WMP` 的训练入口、配置及实际输出目录整理。两套项目均为外部训练器；URDFTools 只读取已经完成的结果。

| 用途 | MyHIMLoco | WMP | 当前导入行为 |
|---|---|---|---|
| 生效配置与 URDF 路径 | `isaaclab_migration/logs/<run>/config.json`，其中 `env.asset.file` | 同左 | 必需；从项目的 `resources/robots/...` 定位 URDF |
| 标量训练曲线 | 同目录 `events.out.tfevents.*` | 同左 | 必需；最多读取 8 个、单个不超过 64 MiB；未声明单位标为“未标注” |
| URDF 与网格 | `legged_gym/resources/robots/<robot>/urdf/*.urdf` 及相邻 `meshes/` | `resources/robots/<robot>/urdf/*.urdf` 及相邻 `meshes/` | 必需；按 URDF 相对网格引用复制并按 SHA-256 存档 |
| 步态回放 | `checkpoint_videos/model_N/preview.mp4`，部分实验在训练目录之外 | `checkpoint_videos/` 或 `isaaclab_migration/outputs/<run>_checkpoints/model_N/preview.mp4`；课程训练可有 `videos/index.json` | 可选；训练目录自动搜索，或在界面另选视频目录；最多选 4 段，每段不超过 128 MiB |
| 评估与验证报告 | `evaluation/evaluation.json`、`*_evaluations/.../evaluation.json`、`gait_metrics.json` 等，结构随实验变化 | `validation.json`、课程 `progress.json`、`videos/index.json` 等；并非统一的独立成功率 | 训练目录顶层现有报告会存档，部分明确标注的数值进入 Agent 摘要；不把这些不同语义的字段自动转换成成功率 |
| 训练检查点 | `model_N.pt` | `model_N.pt` | 不读取、不反序列化、不作为标量证据 |

项目页的“导入原始训练目录”需要选择包含 `config.json` 和 TensorBoard 文件的单次训练目录，并填写自定义算法名称。视频可选；没有视频时仍可查看 URDF 与曲线。导入会保存原始配置、网格、事件文件及选中的视频，生成内部清单。现阶段两套本机项目的机器人都归入四足类别；其它机器人类别需要后续增加选择控件。

**对比边界：**本机 MyHIMLoco 的 `gait_metrics.json` 是轨迹误差、滑动等描述性指标；`evaluation.json` 的 `cases` 是逐任务性能量，不是统一的成功布尔值。WMP 的 `validation.json` 主要记录运行与模型状态校验，不是步态成功率。训练目录本身通常不包含统一格式的独立训练 seed 成功/失败结果、持出测试 seed、逐回合成功布尔值、地形尺寸与推力协议。直接导入项目可以在同网格中并列查看模型，查看曲线和视频，并把已知证据交给 Agent 做描述性分析；统计成功率、置信区间与“完全同条件”结论必须在补齐可核验的独立评估协议后才能给出。原有完整 `manifest.json` 实验包入口继续支持这种严格比较。

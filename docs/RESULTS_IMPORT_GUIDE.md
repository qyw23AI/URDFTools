# 本地外部结果包导入

在桌面应用「评估」页选择实验包文件夹。此入口只读取已经完成的外部实验，不启动训练，不上传文件。数据保存在 Electron 用户数据目录的 `external-results` 下；重启后可重新列出。浏览器预览没有本机文件夹选择接口。

文件夹至少包含：

- `manifest.json`：`bundle_id`、`robot_hash`（原始 URDF SHA-256）、`files`（每个资产的相对路径、字节数、SHA-256）、`model`（`path`、`name`、`version`、`category`、`origin`、`license`）。URDF 文件、`experiment.json` 与 `evidence.json` 必须在清单中。
- `experiment.json`：B01 v1 契约的 `run_id`、`robot_hash`、`robot_category`、`origin`、`algorithm`、`protocol`、`metrics` 等字段。
- `evidence.json`：`schema_version: 1`、B05 比较协议 `protocol`、独立训练种子结果 `seed_runs`，以及 `videos`。每个视频给出清单路径、episode、相机、实验时间偏移、声明帧率和指标事件；应用真实解码帧时间戳后保存事件定位。
- 指标 CSV、JSON、Parquet 或 TensorBoard 文件，按 `experiment.json.metrics` 引用并声明单位。MP4/WebM 视频也列入清单，桌面端可在两组结果对照中播放和跳转事件。超过 128 MiB 的视频保留原始资产和时间报告，但桌面内置播放器暂不读取。

所有资产在复制及解析前验证大小和 SHA-256。`public_import` 模型必须有许可证标识；普通导入不会自动升级为 `verified_reference`。合成夹具只用于流程验证，界面真实参考成绩仍显示 0。

在「评估」页分别选择标准与自有 run 后，应用核对机器人类别、算法、奖励、预算、地形与种子设计；不相符时不输出性能排名。视频和指标均绑定原始 SHA 与 run。当前没有真实、经过审核的参考训练结果，`verified_reference_count` 为 0。普通视频不用于推断扭矩、能耗或机械因果。

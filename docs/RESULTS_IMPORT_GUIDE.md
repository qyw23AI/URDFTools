# 本地外部结果包导入（B08 开发中）

在桌面应用「评估」页选择实验包文件夹。此入口只读取已经完成的外部实验，不启动训练，不上传文件。数据保存在 Electron 用户数据目录的 `external-results` 下；重启后可重新列出。浏览器预览没有本机文件夹选择接口。

文件夹至少包含：

- `manifest.json`：`bundle_id`、`robot_hash`（原始 URDF SHA-256）、`files`（每个资产的相对路径、字节数、SHA-256）、`model`（`path`、`name`、`version`、`category`、`origin`、`license`）。URDF 文件及 `experiment.json` 必须在清单中。
- `experiment.json`：B01 v1 契约的 `run_id`、`robot_hash`、`robot_category`、`origin`、`algorithm`、`protocol`、`metrics` 等字段。
- 指标 CSV、JSON、Parquet 或 TensorBoard 文件，按 `experiment.json.metrics` 引用并声明单位。视频可作为清单资产保存；当前媒体查看仍需手动选择视频与 B07 时间报告。

所有资产在复制及解析前验证大小和 SHA-256。`public_import` 模型必须有许可证标识；普通导入不会自动升级为 `verified_reference`。合成夹具只用于流程验证，界面真实参考成绩仍显示 0。

当前实现还没有把视频记录与数据库 run 自动关联，也没有让桌面页直接发起两组 run 的公平比较。因此 B08 尚未完成正式 gate，需继续开发并验收。

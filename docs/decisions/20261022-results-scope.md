# 用户授权的范围和调度修订

用户要求诊断停机、继续降档，并明确训练在外部平台完成。本次将 B00–B08、D01、X00–X02、Q03/Q04 改为结果导入/对照/复验流程；保留 50 个 IDs 和测试入口。B00 不再依赖仿真编译，B06 改为日志适配。plan-baseline 随用户授权更新，保护今后任务不能自行改图或弱化门禁。

S01 在 20261022T053606Z-S01-45924e33 已返回 completed 且 gates passed，但 Git manifest 拒绝 15,102,119 字节 Chromium 许可证。文件逐字节等于已核验 Electron 39.2.7 官方 zip 中 LICENSES.chromium.html，SHA256 c16ee3cc1aa0d1669a839428ef26869d7a3844a43df505377b85077e1db14396。仅对此路径及哈希放行，其他大文件仍拦截。旧尝试保留，不伪造阶段完成。

当前 S01 修改完整保存于 .scheduler/checkpoints/operator-20261022-scope-v2。修改完成后恢复 checkpoint，由降低等级后的真实 CLI 和 gate 再确认并提交。小时 timer 保留，正在运行不重启，无额外付费 API。

修订验证：63/63 scheduler unittest 通过，50 阶段图 validate 通过，git diff --check 通过。已读取真实 model/list 历史快照确认 Sol 支持 low/medium/high。

# 数据与接口契约

设计 v2。S02 将以下定义实现为 Pydantic/JSON Schema/TypeScript，并固定 schema_version。所有路径均指 project 内受控相对路径或不可伪造的 asset id，禁止在 HTTP 中接受任意主机路径。

| 实体 | 必需字段与不变式 |
|---|---|
| ProjectManifest | schema_version, id, title, robot_snapshot_ids, active_snapshot, source_assets, settings；可迁移并备份 |
| RobotSnapshot | id, content_hash, parent_id, links, joints, materials, assets, extensions, provenance, created_at；不可变 |
| Link | UUID/name, visual[], collision[], inertial{mass,com,orientation,tensor}, cad_part_ids；未知值为 null，带 provenance |
| Joint | UUID/name/type,parent_id,child_id,origin,axis,limits,dynamics,mimic；所有 frame 和 SI 单位已定义 |
| AssetRef | id,sha256,relative_path,mime,size,source_url,source_commit,license_id；路径解析与 hash 校验 |
| ParameterEvidence | value,unit,source_kind,source_ref,uncertainty,assumptions；unknown 与 zero 不同 |
| CadAssembly | id,source_hash,unit,parts[],transforms,groups,materials,joint_candidates,part_mapping；不强制猜关节 |
| EditTransaction | id,base_snapshot,operations[],preview_snapshot,validation,actor,confirmed_at；乐观锁避免覆盖 |
| Finding | id,rule_id,rule_version,category,severity,scope,measured,expected,unit,evidence_ids,assumptions,recommendation,confidence_basis |
| ActuatorProfile | joint_id,type,gear_ratio,torque_speed_curve,continuous/peak_limits,rotor_inertia,friction,latency,source；可含 unknown |
| TaskSpec | id/version,family,terrain,commands,objective,success/termination,evaluation_protocol,unit/scaling |
| ExperimentSpec | snapshot_hash,profiles,task,engine,controller,algorithm,budget,seeds,train/val/test_splits,randomization,code_commit |
| RunRecord | id,spec_hash,status,origin,verification_status,source_bundle_hash,metrics_refs,video_refs,events,resource_usage,hardware,software,seeds,fail_reason |
| ReferenceEntry | id,family,model_asset,source/license,compatibility,task_recipes,verified_runs；smoke 不能升级为 reference |
| Comparison | run_ids,compatibility_verdict,normalization,metrics,intervals,failed_runs,inferences,evidence_refs |
| DesignProposal | base_hash,part/joint_ids,operations,parameter_ranges,evidence_refs,expected_effect,assumptions,validation_runs,status |
| SkillManifest | id/version,families,input/output schemas,preconditions,rules,tool_allowlist,sources,fixtures,compatibility |

API `/v1`：`projects`、`assets/import`、`robots/{id}`、`transactions`、`cad/jobs`、`validation/jobs`、`experiments`、`imports/{id}/resume`、`experiment-bundles/validate`、`references`、`comparisons`、`reports`、`skills`、`agent/sessions`、`jobs/{id}/events`。写请求支持幂等键，版本冲突返回可解释错误；操作参数由 schema 逐项验证。

CLI `urdftools` 与 MCP 工具映射到相同 service 函数，避免不同规则。主要命令为 import、inspect、convert、validate、simulate、results-import、results-export、resume-import、compare、report、skills、doctor、serve。CLI 支持 `--json`，错误对象包含 code/message/details/remediation，不用退出码 0 代表执行失败。

开发任务 schema 与产品实验 schema 分开。阶段配置 `id/title/level/prompt_file/depends_on/tests/acceptance_artifacts/requirements/category`；阶段完成报告包含 status=completed|partial|blocked、summary、checks、artifact_paths、blockers、next_actions、usage。调度器自身执行测试并核验 artifact，模型声称的结果不能替代实际 gate。

结果库扩展的规范字段和可比性约束以 RESULTS_DATABASE.md 为准。ExperimentSpec 记录外部实验配置，不是本地执行训练指令。策略/优化器权重仅可作为外部哈希引用，不执行或反序列化。

## S02 已落地契约（2026-10-22）

源码为 `python/urdftools/core/models.py`。RobotDocument 固定 schema_version=2，
包含稳定 UUID 的 link/joint/material/geometry、显式 SI/右手/Z-up、资产及不执行的扩展文本。
ParameterEvidence 的数值只接受有限数字；unknown 必须为 null，已知零须有显式来源。
时间戳须带时区；不确定度区间须包含对应值。位置 m、RPY rad、质量 kg、惯量 kg*m^2；
COM origin/tensor frame 属于 link，joint origin 属于 parent，axis 属于 joint frame。
张量顺序为 xx,xy,xz,yy,yz,zz。RPY 使用 URDF 固定轴 roll(X)/pitch(Y)/yaw(Z)，
旋转组合 Rz(yaw) Ry(pitch) Rx(roll)，不做显示坐标变换。

图校验要求非空单根连通树，拒绝重复 UUID/同类名字、自环、多个父节点、悬空引用和闭环。
mimic 验证目标、循环和角/线性类型兼容。floating/planar 类型可保存，不表示运动学适配器已实现。
网格必须有显式正 scale，非均匀正缩放可保存，负/零 scale 明确拒绝。
惯量正定、三角不等式和机械合理性属于后续物理规则，并未以本阶段的 schema 通过代替物理通过。

`documents.py` 提供文档/快照读取保存、v1 文档显式 SI 迁移（首次写前以独占创建保存原字节
`.v1.bak`，已有备份拒绝覆盖）、内存 DocumentHistory。快照和内部容器均不可变。
content_hash 是规范化文档 JSON 的 SHA256：Python JSON 浮点表示、UTF-8、对象键排序、
无空白、保留数组顺序、禁止 NaN；不是 RFC 8785。包含资产 sha256 元数据及 provenance，
排除快照 UUID/parent/time。前端不得独立重算哈希，应使用 Python 服务给出的值。
快照读取再次验证 hash。资产字节由 `assets.py` 独立核验 hash/size；文档解析本身不读取资产。

统一事务操作目前为 replace_link/replace_joint，均必须保留目标 UUID。propose 在副本验证完整文档，
返回 preview 和可显示 unified diff；apply 重验 operations/preview、校验 base ID/hash，
需要调用端传入布尔值 True 表示明确产品确认，字符串或数字不作为确认。UI/agent 共用同一路径，失败不改变历史，支持 undo/redo 和分支。
这是核心内存服务，尚无 HTTP 路由、产品预览 UI、多进程锁或持久事务日志；确认参数不是身份鉴权。
ProjectManifest、RobotSnapshot、EditTransaction 和 S02 快照操作的 OperationResult/ServiceError
已生成契约；未来服务结果类型按其阶段扩展，未实现结果库、作业执行或训练器。

生成及核对：

```bash
.venv/bin/python scripts/generate_contracts.py
.venv/bin/python scripts/generate_contracts.py --check
```

输出在 `packages/contracts/schema.json` 和 `index.ts`；TS 是 JSON 输入契约，默认字段可省略，
只读 tuple/字段防止意外修改。Schema 的 graph/hash/跨字段单位/provenance 等语义由 Python
运行时模型校验，TS 静态类型不能替代校验。生成器不支持的 Schema 结构会失败，不退化为 any。
S02 验收实际用 tsc 编译两份 Python 规范化夹具与负向类型断言。
外部结果库的 origin/verification、条件可比性仍以 RESULTS_DATABASE.md 为准；没有导入 fixture 成绩。

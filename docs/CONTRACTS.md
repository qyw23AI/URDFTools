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

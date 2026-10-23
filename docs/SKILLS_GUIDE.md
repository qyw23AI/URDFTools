# URDFTools 项目内技能机制（K00）

技能是**数据清单，不是可执行 Python 插件**。本项目仅发现 `skills/builtin/<id>/manifest.json` 和 `skills/local/<id>/manifest.json` 两级直接子目录；不执行用户提供的脚本，也不自动开放 Shell/CAD 修改权限。

## 用户安装新技能
创建 `skills/local/my_frame/manifest.json`，内容例如：

```json
{
  "schema_version": 1,
  "id": "my_frame",
  "version": "1.0.0",
  "source": "user supplied local rules",
  "description": "Check a right-handed rotation",
  "rules": [
    {"id": "frame_check", "tool": "coordinate_frame", "config": {"tolerance": 1e-8}}
  ]
}
```

在项目根目录运行：

```bash
PYTHONPATH=python .venv/bin/python - <<'PY'
from urdftools.evaluation.skills import discover_skills, run_skill
skills = discover_skills("skills")
print(sorted(skills))
print(run_skill(skills["my_frame"], {
    "frame_check": {"rotation": [[1,0,0],[0,1,0],[0,0,1]]}
}))
PY
.venv/bin/python scripts/accept_phase.py K00
```

支持工具：`inertia_tensor`（3×3 kg·m² 惯量张量，检验对称性、主矩非负与三角不等式）、`coordinate_frame`（3×3 旋转矩阵正交性及右手系）、`contact_force`（法向/切向力 N、摩擦系数与可选穿透深度 m）、`sample_statistics`（至少两个有限样本的均值、样本标准差和描述性正态近似区间）。每个 rule 仅能选择白名单工具和严格配置，所有输入必须显式提供。目录 ID 与清单 ID 一致，拒绝重复 ID、未知字段、未知工具、符号链接和超大清单。

这不是运行时自动加载的 MCP 或桌面扩展；目前由 Python API 调用，后续阶段接入具体机器人规则和 UI。所有测试使用原创数值夹具，不代表真实硬件验证。

## K01 四足结构技能

新增 `quadruped_structure`，使用工具 `quadruped_urdf`，接受**显式 URDF XML 字符串**，不允许任意路径或代码执行：

```python
from pathlib import Path
from urdftools.evaluation.skills import discover_skills, run_skill

skill = discover_skills("skills")["quadruped_structure"]
xml = Path("tests/fixtures/S06/a1_description/a1.urdf").read_text()
report = run_skill(skill, {"quadruped_scan": {"urdf_xml": xml}})
print(report["results"][0]["counts"])
```

可选 `contact_trace` 为 `{"source_kind":"synthetic_fixture"|"simulation"|"measured", "frame":"world", "samples":[{"t_s":0.0, "com_xy_m":[0,0], "feet_xy_m":{"FL":[x,y],"FR":[x,y],"RL":[x,y],"RR":[x,y]}, "contacts":["FL","FR","RL","RR"]}, ...]}`，时间严格递增、至少两帧。此分析仅给出准静态 COM 投影与接触切换计数；双足支撑、动态稳定性和步态质量不能凭此断言。声明 measured 不代表来源已经验证，使用真实数据时须额外保存独立来源证据。四足角色目前遵循 A1/Go2 命名约定；其他命名返回缺失/失败，不擅自映射。

## K02 人形结构技能

新增 humanoid_structure，工具 humanoid_urdf，输入为 humanoid_scan: {urdf_xml: <完整字符串>, contact_trace: <可选对象>}。仅支持 G1 29-DOF 和 H1 19-DOF 命名结构，输出结构/足底/关节/声明惯量/名义质心检查；缺少惯性标签或电机标定的部分保持 unknown。调用示例：

    from pathlib import Path
    from urdftools.evaluation.skills import discover_skills, run_skill
    skill = discover_skills("skills")["humanoid_structure"]
    xml = Path("tests/fixtures/R02/h1_description/urdf/h1.urdf").read_bytes().decode()
    print(run_skill(skill, {"humanoid_scan": {"urdf_xml": xml}})["results"][0]["counts"])

可选 contact_trace 的字段为 source_kind（synthetic_fixture/simulation/measured）、frame="world"、samples（至少两帧，t_s 递增）。每帧需 com_xy_m=[x,y]、contacts=["left","right"] 或子集，以及 sole_polygons_xy_m={"left":[[x,y],...],"right":[[x,y],...]}；可选 torso_rpy_rad=[roll,pitch,yaw] 和 joint_positions_rad={"left_knee_joint":角度,...}。坐标/长度 SI，角度 rad；所有多边形必须已在世界系。接触点不足或面积退化为 unknown。仅输出准静态几何投影与描述性姿态、声明限位比较，绝不以此宣称动态步态稳定。来源标签由调用者声明，需另行验证数据来源。



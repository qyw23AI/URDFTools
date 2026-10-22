# STEP 关节分组与三维预览（C02）

在桌面应用打开“转换”，选择 `.step` / `.stp`。向导只接受来源单位可识别、装配树与零件适配器数量/名称一致的 STEP。零件默认一件一 Link；可把多个零件的 Link 名改成相同名称，再点“应用分组”。该操作会重建父子候选和清除已有确认。

逐个选择父 Link、固定/旋转/直线/连续关节、单位轴向量、世界坐标系中的关节原点（m）、适用的限位，然后勾选“人工确认”。圆柱面线索只作为轴候选，绝不自动确认；无圆柱面的零件以 Z 轴作为待人工修改的占位候选。全部关节确认后，三维预览会自动刷新。修改关节参数会撤销该关节确认，防止旧确认套用到新参数。可保存/载入 JSON 配置，同一个 STEP 文件的 SHA-256 必须匹配。

预览的每个零件显示为轴对齐包围盒。它可用来检查 Link 分组、关节树、轴、原点、限位和动画；它不是精确 CAD 网格，也没有真实材料、质量、惯量或碰撞体，不可用于强化学习或当作最终 URDF。最终可导出的网格/惯量/ROS 包及交叉验证属于 C03。原 STEP 文件不被改写，预览导入到独立的应用数据目录。

命令行也可检查候选：

```bash
.tools/cad-venv/bin/python scripts/cad_joint_wizard.py model.step > draft.json
.tools/cad-venv/bin/python scripts/cad_joint_wizard.py model.step --config confirmed.json --preview preview.urdf
```

`--preview` 要求所有关节在配置中显式 `confirmed: true`。输出的 `preview.urdf` 只用于显示。修改 STEP 后旧配置会因来源 SHA-256 不匹配而拒绝复用。

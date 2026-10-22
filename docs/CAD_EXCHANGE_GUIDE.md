# IGES/BREP 到 STEP 几何桥（C04 开发中）

本地 OCP worker 可把闭合 `.igs` / `.iges` / `.brep` / `.brp` 实体转换为新 STEP 文件，供现有 STEP 检查和 C02/C03 向导使用：

```bash
.tools/cad-venv/bin/python scripts/cad_exchange.py part.iges --output part.step
.tools/cad-venv/bin/python scripts/cad_exchange.py part.brep --brep-unit mm --output part.step
```

BREP 无单位，必须由操作者声明 `mm` 或 `m`；IGES 源单位由 OpenCascade 读入后规范化为 mm。转换后重新载入 STEP，比较实体个数、体积和几何质心，输出 JSON 损失报告。输出路径必须是新文件，源数据不会改写。开放曲面不能产生可靠体积/惯量，故会拒绝进入物理导出链。

**转换损失：** 当前桥只保留实体几何，不保留原装配层级、名称、颜色、材料或关节；需要人工重新分组、填写密度/驱动和确认物理属性。输出是几何中间件，不代表原 CAD 机械设计已无损转换。

本机未安装 FreeCAD 与 sw2robot，因此 `.FCStd`、`.sldasm` 和 `.sldprt` 原生提取目前明确拒绝。FreeCAD 用户可在 FreeCAD 中导出 STEP 后走上述已验证链路。SolidWorks 原生抽取须在 Windows + SolidWorks 上完成；[sw2robot 官方 README](https://github.com/jsk-ros-pkg/solidworks_urdf_exporter2/blob/main/README.md) 说明它可以先提取 `graph.json` 和网格，再于非 Windows 系统做构建/编辑。此项目尚未完成实际 graph 包适配及往返验收，因此 C04 阶段仍在开发中。

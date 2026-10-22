# Ubuntu CAD 互通：FreeCAD、IGES、BREP

桌面应用“转换”工作区可选择 STEP/STP、FreeCAD FCStd、IGES/IGS 或 BREP/BRP。非 STEP 输入在本机隔离进程中转为临时 STEP，再进入现有 Link/关节分组向导；界面显示转换损失，用户需重新确认关节、密度和驱动参数。源文件不改写。

## FreeCAD 安装与离线准备

本项目使用官方 [FreeCAD 1.1.4 Linux x86_64 AppImage](https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.4)，放在 `.tools/FreeCAD_1.1.4-Linux-x86_64-py311.AppImage`（项目忽略，不随源码分发）。程序只接受发布方 SHA-256 `f6dc6ba676e5ac96a565ebc8d657232f94c6158e85b4352141bd1a46f6b43434`。运行 `.venv/bin/python scripts/setup_freecad_worker.py` 会验 hash、解压到 `.tools/freecad-appdir`，不需要修改系统 FreeCAD 或 Python。离线使用已验过的包和目录。

命令行示例：

```bash
.tools/cad-venv/bin/python scripts/freecad_bridge.py bracket.FCStd --output bracket.step
.tools/cad-venv/bin/python scripts/cad_exchange.py part.iges --output part.step
.tools/cad-venv/bin/python scripts/cad_exchange.py part.brep --brep-unit mm --output part.step
```

FreeCAD 桥调用 FreeCAD 自己的无头进程，挑选文档中的有效闭合实体，用 FreeCAD 的 Import 模块导出带多个零件的 STEP；随后现有 STEP 读取器重新导入并校验零件数与单位。BREP 无单位，必须由操作者声明 `mm` 或 `m`；IGES 由 OpenCascade 读取源单位并规范化到 mm。IGES/BREP 桥比较重新导入前后的实体个数、体积和几何质心，并拒绝开放曲面进入物理导出链。所有输出路径必须是尚不存在的新文件。

**损失与边界：** FCStd→STEP 会失去 FreeCAD 的草图、约束及特征历史；IGES/BREP 简化桥会失去装配层级、名称、颜色和材料。任何桥都不能凭几何推断真实关节、密度、电机或训练表现，须人工核对。Ubuntu 上的 `.sldasm` / `.sldprt` 不支持原生提取；用户已选择以 FreeCAD 作为主要 CAD 工具。已从其他软件导出的 STEP/URDF 仍可正常使用。

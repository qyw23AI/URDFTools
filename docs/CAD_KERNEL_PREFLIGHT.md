# C00 STEP/OpenCascade 环境与原型预检记录（历史记录）

> 本文保留早期内核预检记录。后续 C00 技术 gate 已通过，权威验收结论见 [docs/acceptance/C00.md](acceptance/C00.md)；是否标记阶段完成仍由调度器复核。

日期：2026-10-22。本文记录 C00 正式验收前的内核预检实验，不替代 [C00 正式验收记录](acceptance/C00.md)，也不单独构成阶段完成声明。

## 独立环境与固定版本

CAD 内核未安装到系统 Python 或现有 `.venv`，而是项目内隔离的 `.tools/cad-venv`：
- CPython 3.12.14；
- `cadquery-ocp-novtk==8.0.1.1.0`、`cadquery-ocp-proxy==8.0.1.1.0`；
- `numpy==2.3.4`（供待验证的 STEP 适配层使用）。

起初试装 `cadquery-ocp==8.0.1.1.0` 并使用 `--no-deps`，真实 `import OCP` 报 `libvtkWrappingPythonCore3.12.so` 缺失，**不是成功的 CAD 内核**。随后在同一个隔离环境内卸载它，改为固定无 VTK 版本：`import OCP`、STEP XCAF reader/writer、几何测量均已实际运行。无 VTK 版本是为了避免纯 STEP CAD 检查引入额外大型绘图依赖，并非宣称兼容所有 OCC/FreeCAD 插件。

上游来源/许可线索（正式重新分发需复核）：[cadquery-ocp PyPI](https://pypi.org/project/cadquery-ocp/)、[ocp-build-system](https://github.com/CadQuery/ocp-build-system)；参考 [edsamsankey/step2urdf](https://github.com/edsamsankey/step2urdf) 的本地化 STEP/URDF 方案（MIT 许可），不得把参考代码或软件当成已交付产品。

当前复建入口已更新为哈希锁定安装；请按 `docs/TOOLCHAIN.md` 使用：

```bash
.venv/bin/python scripts/setup_cad_worker.py
# 已有 .tools/cad-wheelhouse 时可离线：
.venv/bin/python scripts/setup_cad_worker.py --offline
```

## 实际 STEP 与单位测试

- 通过 XCAF 原生接口生成一个 2 零件命名 STEP 装配；`UpdateAssemblies` 后写入再读回，成功发现 **1 根装配、2 个组件**。第二组件变换读回 **X = 50 mm**。
- `STEPControl` 分别创建声明长度单位 **millimetre** 和 **metre** 的 STEP。读取端通过 `FileUnits` 返回原始单位，转入 CAD 内核后两者同样量取 **20.0000002 mm** X 长度，归一化应报告为 0.020 m；BRep 包围盒浮点误差约 2e-7 mm。
- 项目自制 `scripts/generate_c00_fixtures.py` 真正生成 `tests/fixtures/C00/two_part_mm.step` 与 `single_part_m.step`，源 SHA256 固定在 `tests/fixtures/C00/manifest.json`。实际 `PYTHONPATH=python .tools/cad-venv/bin/python` 调用 `urdftools.cad.step2urdf_adapter.load_step`：
  - 两零件装配：BasePart 20×10×5 mm，颜色约 (0.8,0.2,0.1)，COM (10,5,2.5) mm；OffsetPart 10×6×4 mm，颜色约 (0.1,0.4,0.9)，平移体现在 COM (55,23,12) mm。
  - 单零件米单位文件：MeterPart 1 个、20×10×5 mm、无颜色 **None**（未知），COM (10,5,2.5) mm。没有把缺失颜色猜测为固定值。
- 这些是**原创合成夹具**，不能代表 SolidWorks 实际装配、多层嵌套模型、质量密度/材料、运动关节定义或 URDF 正确性；需要后续 C00 运行的真正 gate 证明。

## 后续工作边界

STEP 没有普适的完整运动学关节/密度信息。C00 仍需要集成可审计的文档结构接口、单元/负向测试、异常输入/深层装配以及整个阶段声明测试，并验证与当前 Electron“转换”工作区的真实连接；C01–C03 才负责基于真实材料密度的质量惯量、联接与自包含 URDF 导出。**没有执行或宣称任何 RL 训练/结果、真实机械设计或动力学评估。**

本预检未运行调度器、未修改 `.scheduler/state.json`、未创建 Git commit，也未修改全局 Python、驱动或现有机器人项目文件。

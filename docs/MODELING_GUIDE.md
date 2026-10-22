# 参数化 CAD 核心（M00）

M00 提供本地命令行与 Python API，图形交互在 M01。使用 [build123d 0.13.0](https://pypi.org/project/build123d/) 和独立 `.tools/model-venv`；运行 `.venv/bin/python scripts/setup_model_worker.py` 安装 `model-requirements.lock` 中的精确版本，已装好时可用 `--verify` 检查。开发环境不修改系统 Python。

输入是受限 JSON 配方而非任意 Python 程序。每个零件显式给出名称、材料名和密度（kg/m³），尺寸使用 mm。支持矩形/圆形/多边形草图、矩形圆孔、拉伸、旋转、加/减盒体与圆柱体、按 X/Y/Z 平行边圆角。生成有效闭合 BREP 后用 OCP 计算 SI 质量、质心、惯量；输出逐零件 STEP/STL 并重新读 STEP 检查体积。

```bash
.tools/model-venv/bin/python scripts/model_project.py tests/fixtures/M00/two_part_recipe.json --project /tmp/my-robot-cad --expected-revision 0
```

成功后项目的 `current.json` 指向只读版本目录 `revisions/000001/`，包括配方、报告、每个零件的 STEP/STL。修改配方时使用当前 revision 作为 `--expected-revision`，会生成下一版；错误草图、旧 revision、失败导出均不会替换当前版本。调用方可通过复制旧配方再次应用来“回滚设计”，原版仍保留。不同物理零件之间的关节和装配位置将在 M01 与现有 C02/C03 向导中确定；M00 不推断训练适用性。

`model-requirements.lock` 锁住所有 58 个 Python 包的版本，但当前未生成 wheel SHA-256 仓库，首次安装仍需可信的软件源；后续发行质量阶段应补充哈希和离线包验证。

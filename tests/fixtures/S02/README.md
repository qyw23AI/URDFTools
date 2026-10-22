# S02 原创领域文档夹具

`build_fixtures.py` 生成双连杆、九 link/八 joint 四足树和显式 SI 的 v1 文档。
本项目为这些原创夹具提供 CC0-1.0 授权；没有复制任何机器人/CAD/第三方模型。
数值是人为选取的确定性测试常数，provenance.source_kind=default、origin=synthetic_fixture；
不是实测参数、真实训练结果或参考成绩。质量总和分别为 3.25 kg 和 8.875 kg。

```bash
.venv/bin/python tests/fixtures/S02/build_fixtures.py
python3 scripts/accept_phase.py S02
```

v1 的唯一历史布局差异是 `schema_version:1` 与 `unit_system:"SI"`；其余 frame、
provenance 均已显式。迁移只重命名此字段并更新版本，不能推测 mm、缺失 frame 或来源。

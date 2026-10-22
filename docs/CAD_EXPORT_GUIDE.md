# STEP 导出 URDF / ROS 包

在桌面应用“转换”工作区选择 STEP，分配 Link 和关节并逐项人工确认。为每个 CAD 零件填写经过材料核对的密度（kg/m³）；活动关节还需填写正的最大力/力矩及最大速度。点击“导出并交叉校验 URDF / ROS ZIP”后选目标文件。应用从 STEP 精确实体计算质量、质心和惯量，生成 STL 视觉网格及保守的轴对齐碰撞盒，重新解析导出包，用 MuJoCo 编译原始 URDF 和注入自由关节的浮动基座变体。只有校验成功才保存 ZIP。保存的配置 JSON 也包含密度字段，导出时仍需检查实际材料。

ZIP 根目录为 `urdftools_robot/`，包含 `robot.urdf`、`meshes/*.stl`、`metadata.json`、`package.xml`、`CMakeLists.txt`。目录导出可使用 CLI：

```bash
.tools/cad-venv/bin/python scripts/cad_export_package.py model.step --config confirmed.json --densities densities.json --output robot.zip
.tools/cad-venv/bin/python scripts/cad_export_package.py model.step --config confirmed.json --densities densities.json --output robot_dir --format directory
.tools/sim-venv/bin/python scripts/validate_cad_package.py robot.zip
```

`densities.json` 用 STEP 中的确切零件名作键，例如 `{"BasePart":2700,"OffsetPart":2700}`。独立 MuJoCo worker 使用 `sim-requirements.lock` 哈希锁；在线首次安装运行 `.venv/bin/python scripts/setup_sim_worker.py`，缓存 wheel 后可使用 `--offline`。ROS 2 环境存在时，解压 ZIP 后运行 `colcon build --base-paths <解压目录>`。

**关键限制：** 密度和驱动参数是用户输入，软件无法从 STEP 证明其真实值；碰撞盒是代理，不是精确接触几何。尚未验证摩擦、接触、执行器控制、传动和硬件匹配，报告始终为 `training_ready: false`。MuJoCo 直接编译原始 URDF 时根 Link 为固定基座，其质量不进入动态 body mass；交叉校验为浮动基座显式加入自由关节，再核对总质量和质心。参见 [MuJoCo Python API](https://mujoco.readthedocs.io/en/stable/python.html) 和 [模型编译选项](https://mujoco.readthedocs.io/en/latest/XMLreference.html)。生成包的许可栏保持 `UNSPECIFIED`，分发前须由所有者确定 CAD/机器人模型及网格的授权。

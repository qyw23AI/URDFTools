# URDFTools 查看模块用户操作指南

## 启动开发版（Ubuntu）

```bash
cd ~/URDFTools
bash scripts/launch-dev-desktop.sh
```

此命令在项目内用固定本地 Node/Electron 构建并启动，**不是最终的系统级安装**。软件使用本地 Python 和 Electron 沙箱，不需要把 CAD/URDF 上传到网站。

## 从 URDF 到可视化

1. 在主界面的「查看」页，拖入 **包含 `.urdf`、`package.xml` 和 mesh 的整个文件夹**；也可以通过“选择文件夹”按钮导入。单独选择 URDF 文件只能得到该文件，如果引用外部网格，应选择文件夹。
2. 可以拖入 ZIP；保持包目录层级，保证 URDF 中的 `package://` 引用可以从 ZIP 内解析。若发现多个 URDF，必须在列表里选择要显示的模型。导入报告会显示找不到的 mesh/纹理和具体 URDF 位置。
3. 导入报告处于“资源检查通过”且三维资源加载完成后，使用鼠标左键旋转、滚轮缩放、右键平移视图；侧边结构树展开 Link / Joint，点击对应节点会定位到当前姿态下的位置。
4. Visual 和 Collision 可以独立显示；Collision 会以红色线框叠加。选择某个 Link 后可隔离显示以检查网格与碰撞体差异，操作不会修改原始 URDF。
5. “质量、质心与惯量”显示来自 URDF 的**显式数值**。没有声明的质量、COM、惯量会标记为未知（不是零）。选择 Link 看局部质心、世界坐标以及轴对齐视觉包围盒，单位为 m、kg、kg·m²、rad。
6. 调整关节滑块观察姿态（位置限位来自 URDF；continuous 的滑块范围只是 UI 交互范围），需要时重置视角并导出 PNG。导出是截图，不会保存机器人新 URDF。

## 可直接试用的开源参考模型

项目提供仅用于开发验收的参考文件：

- Go2：`tests/fixtures/S06/reference_models/go2_description/`（选择该文件夹）
- G1：`tests/fixtures/S06/reference_models/g1_description/`（选择文件夹；或者运行 S06 验收后导入 `artifacts/S06/input-zips/g1_description.zip`）

来源、提交、版权和文件哈希见 `tests/fixtures/S06/reference_models.json`，以及 `docs/acceptance/S06.md`。这些开源文件**不能代表任意 RL 任务的标准答案**。

## 限制

目前这是**只读查看与粗略诊断**：Link 包围盒不是 SolidWorks CAD 的精确机械尺寸；Collider 显示不是碰撞动力学仿真，质量/惯量仅显示源字段，不能判断结构是否适合 Isaac Lab 或 PPO 训练。STEP/CAD 转换、URDF 编辑与安全 Agent、Pinocchio 动力学或训练结果对照是后续阶段。商业模型/私人文件默认只在本机处理。

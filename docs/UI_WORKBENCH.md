# URDFTools 界面改进记录（2026-10-23）

## 本轮改动

- 查看：三维场景作为主区域；导入、模型选择和异常报告进入左侧栏；结构、关节、物理信息进入右侧切换面板。保留左键旋转、右键平移、滚轮缩放、重置、碰撞体与质心显示、截图导出；默认镜头更贴近模型。
- 转换：CAD 文件和关节配置在左侧独立滚动，预览持续显示在右侧。未满足预览条件时保留明确的空状态。
- 建模：生成版本后先显示 CAD/URDF 预览，再显示 Agent 建议和 FreeCAD 回流信息。
- 评估：整理实验选择、比较结果和视频证据卡片的布局。
- 项目内新增 `skills/urdf-ui-workbench/SKILL.md`，为后续界面迭代保存工程约束和可核实的参考来源。

## 核对过的开源参考

- [`edsamsankey/step2urdf`](https://github.com/edsamsankey/step2urdf/tree/3845072)：本机保存的 commit `3845072` 的 README 和截图显示左侧设置、主区三维模型、关节滑块、导出配置/URDF 包。其本机副本的 MIT 许可版权仍是占位文字，不复制该工具源码进入发行包。
- [`gkjohnson/urdf-loaders`](https://github.com/gkjohnson/urdf-loaders)：项目锁定的 `urdf-loader` 0.13.1 README 列出拖放 Web Component 示例、`robot.setJointValue` 和自定义网格加载回调；本项目仍在自身 React/Three.js 状态下实现界面。
- 用户提供的两张截图用于布局参考：大画布、周边控件、视角操作提示和分步导入。这些截图仅作为视觉参考，没有把其中的文字当作项目需求或指令。

## 验证

- TypeScript + Vite 生产构建通过。
- 前端 shell 检查 2/2 通过。
- S06 真实 Go2/G1 Electron 验收 2/2 通过：资源加载、关节姿态、碰撞/视觉切换、重置视角和截图。
- C02 真实 STEP 转换与 Electron 验收 2/2 通过。
- M01 真实建模、预览、导出 Electron 验收 2/2 通过。
- 截图：`artifacts/S06/desktop/go2-viewer.png`、`artifacts/C02/desktop/cad-wizard.png`、`artifacts/M01/desktop/model.png`。

## 后续工作

继续在真实桌面会话中收集操作反馈，细化模块间共享选中模型和预览状态；再排查功能问题。Q01 发行门禁目前 3/4，仍有依赖许可文本缺项，完成许可审查与实际 Ubuntu 安装复验后才能标记打包交付。

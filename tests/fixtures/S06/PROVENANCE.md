# S06 官方参考模型来源与许可记录

## 来源

- 上游仓库：https://github.com/unitreerobotics/unitree_ros
- 固定 Git commit：`5994d4faef0a9cadd3287f8de0199a67eeb2a259`
- 仓库根目录许可：BSD 3-Clause；保留原始许可文本于本目录的 `UNITREE_LICENSE`。
- 测试用途：验证 URDFTools 的文件夹/ZIP 导入、package:// 与相对网格路径解析、真实模型三维加载、关节与碰撞体交互。参考模型仅存于测试夹具，不会自动打入正式运行时应用包。

## 模型清单

| 模型 | 上游文件 | URDF 中 Link / Joint 数 | 网格引用 |
|---|---|---:|---:|
| Unitree Go2 | `robots/go2_description/urdf/go2_description.urdf` | 42 / 41 | 7 个唯一 DAE |
| Unitree G1 29-DoF | `robots/g1_description/g1_29dof.urdf` | 40 / 39 | 36 个唯一 STL |

实际文件 SHA-256、大小、每个网格引用及上游路径记录在 `reference_models.json`。测试会核对原始 URDF 哈希、每个 fixture 文件哈希、包许可、导入状态和资源解析状态。

Go2 的 package.xml 来自上游目录。该 commit 中 G1 描述目录未提供 package.xml，因此测试夹具增加了一个最小的本地 package.xml 包装，使导入器可以将目录识别为 `g1_description` 包；G1 原始 URDF 和所引用 STL 文件保持逐字节不变。ZIP 测试会把此包放在归档中的 `g1_description/` 目录下，验证包 URI/相对路径不会逃逸导入 bundle。

## 许可边界

此仓库的根 LICENSE 为 BSD 3-Clause，许可文本已保留。该记录仅说明本测试所用文件的上游来源和仓库级许可，不替代对任何未来新增纹理、第三方网格或其他仓库资源的逐项许可检查。若将模型用于发行包，应重新核查对应 commit、文件来源和许可证义务。测试数据不是 Unitree 官方校准声明，也不能证明 URDF 惯量/碰撞数据与任意实物版本完全一致。

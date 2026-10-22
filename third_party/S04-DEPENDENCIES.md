# S04 三维查看依赖 / 开发阶段来源核对

2026-10-22。项目 `package-lock.json` 固定精确版本、下载 tarball URL 和 Subresource Integrity；未将上游源码整仓复制。当前**不是发行许可完整清关**，Q01 前还需完成所有打包组件 NOTICE 清单与 provenance 复核。

| 包 | 固定版本 | 仓库/许可 | 用途 |
|---|---|---|---|
| three | 0.180.0 | https://github.com/mrdoob/three.js · MIT（npm 安装文件 `node_modules/three/LICENSE`） | 场景、相机、OrbitControls、OBJLoader |
| urdf-loader | 0.13.1 | https://github.com/gkjohnson/urdf-loaders · Apache-2.0；Caltech/JPL copyright、美国政府赞助说明需保留 | URDF 解析、运动树、默认 STL/DAE |
| @types/three | 0.180.0 | https://github.com/DefinitelyTyped/DefinitelyTyped · MIT（npm 安装文件 `node_modules/@types/three/LICENSE`） | TypeScript 类型 |

注意：urdf-loader 的 npm 发布 tarball 不含根目录 LICENSE，需从官方仓库拷贝实际 Apache-2.0 许可和特有 notice 后随发行包附带。依赖安装曾出现 registry.npmjs.org ECONNRESET，随后明确使用 https://registry.npmmirror.com/ 完成且锁定 integrity。未自动上传任何用户 CAD。真实许可证及第三方 transitive 包的发行义务仍需独立检查。

# 第三方来源与许可账本

`manifest.json` 记录 S01 的 309 个开发组件：Python wheels、web/desktop npm 依赖、npm 工具 bundled 依赖及 Python/Node/Electron runtime。版本和发布产物 SHA256/SHA512 固定；未知源码 commit 明确为 null。`notices/` 保存原始许可证及哈希，第三方代码未修改。Electron 解压只调整文件权限（不授予 setuid/setgid）。

C00 新增 step2urdf 的 CAD 读取适配器：上游 `edsamsankey/step2urdf` 固定到 commit `3845072d29c0cdbd12a9b3c65808440163e32130`，只将 `cad.py` 原样复制为 `python/urdftools/cad/step2urdf_adapter.py`；原始 MIT 文本和文件 SHA256 保留在 `step2urdf-adapter/`。上游 LICENSE 的版权行仍为 `YOUR NAME HERE` 占位符，因此只记录为开发期依赖，**Q01 发行许可审查必须处理该缺口**，本项目不自行伪造作者或版权声明。CAD worker 的 OCP/NumPy/PyYAML 版本与 wheel hashes 独立记录在根目录 `cad-requirements.lock`，不属于 S01 的 309 项应用基础依赖图。


重建：`python3 scripts/third_party_inventory.py`。输入为锁、项目内安装包、已校验 wheels、npm tarball 元数据和 Electron 固定归档。Electron 安装文件必须逐项匹配已验归档才生成 74 文件哈希表；SHA256 还与 GitHub 发布 API 和官方 SHASUMS 比对。来源、镜像和锁审查在 `artifacts/S01/electron-download-review.json`。Electron MIT 与完整 Chromium notices 已保留（Chromium HTML 约 15 MB）。Node 固定标签 combined LICENSE 经官方 GitHub API 取得，源/blob/hash 在 `artifacts/S01/node-license-source.json`。

这不是发行许可审查完成声明。keyv@4.5.4 的 npm 包仅声明 MIT、没有附带许可全文，固定版本源码 tag/commit 未确认，暂不编造原文或 commit。部分 npm 内部包需要按父包许可复核，Python build-tool wheel 中的 bundled notices 已保存但尚未逐一展开成组件。Python/Node seed 也没有完整上游二进制构建 provenance。上述缺口仍需在 Q01 发行审查解决，不能因开发安装与运行通过而宣称可重新发行整个依赖集合。

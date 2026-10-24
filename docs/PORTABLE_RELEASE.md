# URDFTools Ubuntu 便携版（Q01 技术候选）

这是 x86_64 Ubuntu 的 `.tar.zst` 便携目录，不是 AppImage；第三方许可尚未审查完毕，暂不应公开再分发。随包携带 CPython 3.12.14、Electron 39.2.7 和各 Python worker，不使用 Codex CLI、Codex 缓存或系统 Python。

在安装有 tar/zstd 的 Ubuntu 系统运行：

```bash
tar --zstd -xf URDFTools-0.1.0-linux-x86_64.tar.zst
cd URDFTools-0.1.0-linux-x86_64
./launch.sh
./launch.sh --check
./launch.sh --cli doctor --json
```

「查看」页的「打开内置示例」会经真实本地导入器打开原创两连杆模型（2 link、1 revolute joint、OBJ 网格）。示例质量惯量仅供演示。便携目录需要当前用户可写：启动器会将随包 Python 环境重定位到解压路径，不能直接在只读 AppImage 挂载点使用。用户数据位于当前用户 `~/.config/urdftools-desktop`。升级可解压新目录并行验证；卸载删除旧目录，用户数据默认保留。

已验证新目录、干净 HOME、不可用外部代理下的 Electron + Python 导入与渲染，但未进行物理断网、独立 Ubuntu 机器或 GNOME 桌面人工体验。FreeCAD 外部程序未随包提供，SolidWorks 原生装配依赖 Windows。仍须补齐所有第三方/原生库许可和完整 CAD/Agent 回归；Q02 再执行桌面启动器与收藏夹安装。

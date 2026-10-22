# S01 开发工具链

Ubuntu/Linux x86_64 开发骨架使用独立 Python 3.12.14、Node 24.19.0、npm 10.9.9 和 Electron 39.2.7。Python/Node 二进制版本及 SHA256 在 `toolchain.json`；Python wheels、web npm、desktop npm 和 Electron Linux 归档分别由 `requirements.lock`、根 `package-lock.json`、`apps/desktop/package-lock.json`、`apps/desktop/runtime-lock.json` 锁定。机器人产品功能仍按后续阶段实现。

运行时复制到项目 `.tools/python`、`.tools/node`，npm 在 `.tools/npm`，venv 在 `.venv`。不修改系统环境。当前 Python/Node 使用明确提供的本地开发 seed；只接受已审查的二进制哈希，不隐式更换版本。尚未建立完整上游构建链，不能当作最终离线发行归档。复制排除 site-packages、node_modules 和绝对/悬空符号链接；venv 的 base_prefix 实测指向项目副本。

新 checkout 安装：

```bash
python3 -E scripts/bootstrap.py --offline \
  --python-runtime /path/to/python-3.12.14 \
  --node-runtime /path/to/node-24.19.0 \
  --npm-source /path/to/npm-10.9.9 \
  --wheelhouse /path/to/locked-wheels \
  --npm-cache /path/to/npm-cache \
  --electron-cache /path/to/electron-cache
```

本机上述缓存位于 `.tools` 对应目录。Electron 缓存必须含 `runtime-lock.json` 指定名称和 SHA256 的 zip。bootstrap 默认也安装 desktop npm 依赖并调用 `scripts/setup_desktop.py`；缺归档、归档损坏、依赖缺失均非零且说明补齐入口。支持单独重装桌面：

```bash
python3 -E scripts/setup_desktop.py --offline
```

所有 npm 安装使用 `ci --ignore-scripts`，用户/global 配置替换为项目内独立空文件；不继承 registry 凭据、API key、NODE_OPTIONS 或 Python 注入变量。pip 使用 hash-locked wheels 和禁用配置的 venv，不隐式下载构建后端。引导解释器使用 `-E`；脚本对子进程使用环境白名单。删除项目 `.tools`、`.venv`、两处 `node_modules` 即可回退，不覆盖输入 seed。

联网准备缓存时，在 Python 3.12/Linux x86_64 执行固定锁的 wheel 下载，并分别在根目录和 `apps/desktop` 执行 npm ci（使用干净环境和显式公开 registry/config/cache）：

```bash
python3.12 -m pip download --require-hashes -r requirements.lock -d /path/to/locked-wheels
node /path/to/npm/bin/npm-cli.js ci --ignore-scripts --no-audit --no-fund --cache /path/to/npm-cache
```

运行时下载是独立、显式步骤，不由安装钩子自动下载。Electron 来源及归档 SHA256 在 runtime lock，官方 SHASUMS 原文保存在 `third_party/electron-SHASUMS256.txt`，发布 API 元数据在 `artifacts/S01/electron-release-assets.json`。本轮 GitHub 资产直链 TLS 失败，从公开 npmmirror 获取相同固定归档，并同时核对 GitHub API digest 与官方 SHASUMS；没有修改摘要或使用未校验运行时。zip 文件逐项安全解压，保留可执行位，移除 setuid/setgid。安装内容逐项对照已验归档，74 项文件哈希保存在 `third_party/electron-runtime-files.json`。

根 web 锁曾由 `scripts/lock_cached_npm.cjs` 从已校验的公开 tarball 元数据恢复，24 包 Linux 图已实际 `npm ci --offline`。恢复器不支持版本冲突；日后更新优先使用 npm 官方 resolver。desktop 锁由 npm 官方 resolver 生成，70 包均为公开 registry HTTPS 来源且带 integrity；再次离线 ci 已通过。许可来源、内容和限制见 `third_party/README.md`。

```bash
.venv/bin/urdftools doctor --json
URDFTOOLS_SESSION_TOKEN=<至少32字符的随机凭据> .venv/bin/urdftools serve
PATH="$PWD/.tools/node/bin:$PATH" .tools/node/bin/node .tools/npm/bin/npm-cli.js run build
PATH="$PWD/.tools/node/bin:$PATH" .tools/node/bin/node .tools/npm/bin/npm-cli.js run preview
PATH="$PWD/.tools/node/bin:$PATH" .tools/node/bin/node apps/desktop/node_modules/electron/cli.js apps/desktop
python3 scripts/accept_phase.py S01
```

服务仅绑定 127.0.0.1、动态端口，所有 HTTP 请求需 Bearer token，含 Origin 请求拒绝；启动行不输出 token。当前 renderer 不直接访问服务，Electron 主进程执行健康检查并管理服务生命周期。关闭 Node integration，启用 contextIsolation 和 sandbox，拒绝新窗口与导航。

桌面 gate 每次用固定工具链构建源码，校验已安装 Electron 文件，在临时 HOME、无用户 DISPLAY/WAYLAND_DISPLAY/XAUTHORITY 的环境运行 Chromium `--ozone-platform=headless --disable-gpu`。真实 React 挂载、查看→评估点击、preload 隔离、sandbox 和 PNG 截图均有断言；不使用 `--no-sandbox`。这是本地软件渲染验收，不能推断用户 GNOME 会话、GPU/WebGL 或最终安装已验收。单独入口为 `python3 scripts/desktop_smoke.py`。

验收器从 `scripts/acceptance_manifest.json` 注册阶段，S01、S02 已注册实际验收；未知/未来阶段返回 2。每个 stage 有界执行，超时清理整个进程组，保存独立 UTC 时间戳日志及 counts。空测试、全 skip、失败和 expected failure 均不通过。集成验收在全新含空格目录安装，验证 CLI、真实 HTTP 鉴权/Origin、Vite preview 与生产 bundle、SSR、离线失败和真实桌面渲染。机器报告在 `artifacts/acceptance/S01.json`，历史失败保留在 `artifacts/S01/runs/`。

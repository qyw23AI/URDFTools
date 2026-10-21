# 项目运行与交接

源码根目录 `/home/qyw/URDFTools`；架构于 2026-10-22 生成。当前实现从 S00 开始，由调度器启动独立 Codex CLI，按 `scheduler.json` 的 level 实际指定模型。

现有可用命令：

```bash
cd ~/URDFTools
python3 scheduler.py status
python3 scheduler.py run --dry-run
systemctl --user status urdftools-dev.timer
systemctl --user start --no-block urdftools-dev.service
journalctl --user -u urdftools-dev.service -n 50
```

`run --dry-run` 在旧调度器中只看第一项，未运行模型。S00 完成前 `validate/doctor` 等为计划新增命令，不能当作现有功能。

每阶段的验收记录在 `docs/acceptance/<id>.md`，总进度在 `PROGRESS.md`，机器状态在 `.scheduler/state.json`。源码本地 Git 提交是断点；日志在 `.scheduler/runs/`。用户可手动停止 service 保留 checkpoint；暂停定时器使用 `systemctl --user stop urdftools-dev.timer`（停止 timer 不会自动杀死正在运行的 service）。

认证：使用现有 `codex login` 的 ChatGPT 会话。会话过期需用户自行重新登录；不得把 token 写进项目。CLI app-server 额度读取由 S00 实测，无法读取时明确显示 unavailable，按实际限额事件退出。不要自动兑换重置次数。

开发引导观测到的可用路径（S01 要验证并写工具链清单）：

- Codex CLI：`/usr/lib/chatgpt/resources/codex`（0.160.0）
- Python 3.12：`/home/qyw/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`
- Node 24：`/home/qyw/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node`
- pnpm：`/home/qyw/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm`

CLI 子进程可能没有交互 shell 的 PATH；引导脚本显式处理路径，禁止修改全局环境去影响其它项目。产品 venv、依赖 lock 和安装包必须独立，不依赖上述 Codex 缓存的长期存在。

硬件：GPU 驱动当前不可用，仅记录检测结果；不自动重装驱动。纯 CPU 功能继续实现，GPU 实验保留 waiting_hardware。训练队列默认节流、可断点续训，不把未跑的全量基准报告为完成。

开发目录在当前聊天 writable root 外；已有用户明确授权该路径与定时部署。沙箱需要时按授权申请命令执行提升，不通过 symlink/全局不受限 sandbox 绕过审批。若自动审查拒绝，写出具体阻塞，不无休止重复命令。

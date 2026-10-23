# URDFTools 使用网页 ChatGPT + WebCodex Agent

本方案已替代桌面版原先的 Codex CLI 自动生成建议入口。**不需要 Codex CLI 剩余额度、API Key 或外部付费模型服务**。它复用用户已连接的 **web-codex-tunnel** 插件，使用当前 ChatGPT 网页对话完成自然语言推理。正常 ChatGPT 聊天本身仍受所属套餐及平台限制；本方案并不解除 ChatGPT 的使用额度。

## 系统结构与真实边界

`URDFTools Electron UI → 本地 Python 校验 → artifacts/WebCodexAgent/<32位请求ID>/request.json → 用户在 ChatGPT 对话粘贴提示 → @web-codex-tunnel 读取项目请求 → ChatGPT 生成 JSON → @web-codex-tunnel 执行 submit 回写 → Python 本地验收 → 桌面端点击“检查回复” → 只读诊断或 CAD 独立预览 → **用户确认**才应用模型`。

WebCodex 是由 ChatGPT 网页调用的**受控项目工具通道**，并非 Electron/本地 Python 可直接调用的 ChatGPT 推理 API。目前尚不支持打开桌面应用后由网页模型在后台自动持续接单，也不允许偷用用户浏览器 cookie、未文档化内部接口、向外部服务上传完整 CAD，或绕过平台额度。因此请求需要用户在当前 ChatGPT 网页对话中主动粘贴并发送；WebCodex 提交结果后，桌面端可查询本地文件状态。

## 使用步骤

1. 在 Ubuntu 项目目录运行 `./scripts/launch-dev-desktop.sh`，并确保网页 ChatGPT 已连接用户授权的 `web-codex-tunnel` 插件（项目 `agent:qyw-36deaa6097074660:urdftools-83bf0d34`）。
2. **URDF 分析**：在「查看」导入 URDF 或资源文件夹。右侧 WebCodex Agent 将提供「分析当前导入 URDF」，执行本地静态规则，只复制来源哈希、已发现问题、link/joint 位置和 SI 数值；**不会自动把整个 URDF、网格或用户文件发送给模型**。未导入时只能调用明显标注 `synthetic_fixture` 的 D03 合成示例。
3. **CAD 建模**：在「建模」构建当前 CAD 版本后，输入自然语言修改要求，点击「创建 WebCodex 建模请求」。本地请求会包括你当前**完整的 CAD 参数配方**（名称、材料密度、草图/挤出、位置），因此请在确认愿意与该 ChatGPT 对话共享这些参数后再点击。
4. 点击「复制 ChatGPT/WebCodex 提示」，粘贴到 ChatGPT 网页会话并发送。模型通过插件获取 `request.json`，在网页会话中分析，生成受限 `answer` 并通过插件运行 `scripts/webcodex_agent_bridge.py submit --id ... --response ...`。**请勿让模型直接改写源 CAD、`current.json`、项目工作区或调度器。**
5. 回到桌面点「检查网页回复」。诊断建议显示五类候选原因、可解析的 evidence ID、缺失与反证，状态保持 `advice_only`。建模建议必须经 `_validate_suggestion`、版本核对和实际 `preview_recipe` 生成独立 STEP/STL 预览，状态保持 `preview_only`。审阅差异、重算的质量/惯量后才能点击「接受建议并生成新版本」。

## 当前命令接口

```sh
# 合成 D03 示例（不代表你的机器性能）
.tools/model-venv/bin/python scripts/webcodex_agent_bridge.py create-analysis --instruction "请核对证据并建议复验"

# 真实导入 URDF，本地静态检查后才生成隐私受限的网页任务
.tools/model-venv/bin/python scripts/webcodex_agent_bridge.py create-urdf \
  --urdf /path/to/robot.urdf --instruction "检查关节轴、惯量和连杆拓扑"

# 已构建的 CAD 版本（需版本匹配）
.tools/model-venv/bin/python scripts/webcodex_agent_bridge.py create-model \
  --project /path/to/modeling/project --revision 1 --instruction "只调整腿长，不改密度"

# 通过 WebCodex 读取项目中的 request.json 后，由 ChatGPT 生成结构化 response.json
.tools/model-venv/bin/python scripts/webcodex_agent_bridge.py submit \
  --id <请求ID> --response /path/to/response.json
.tools/model-venv/bin/python scripts/webcodex_agent_bridge.py status --id <请求ID>
```

网页回复必须为 `{"schema_version":1,"request_id":"...","request_sha256":"...","answer":{...}}`。对于诊断，`answer` 须包含 `schema_version,case_id,summary,causes,recommendations,limitations`，保持 D03 原因和引用原样并仅提出人工复验。对于建模，`answer` 须为 `schema_version=1,action="replace_recipe",expected_revision,recipe,rationale`，不得新增脚本执行等非法字段。请求 ID、不可变 SHA、允许的来源证据与 CAD revision 任一不匹配就拒绝。

## 安全、来源与限制

- 私有数据的队列位于被项目 `.gitignore` 忽略的 `artifacts/WebCodexAgent/`；只有用户主动在网页会话中提交请求，模型才读取该请求。仍应视 ChatGPT 为外部数据接收方，不要放入密码、密钥或不愿发送的商业 CAD。
- 不通过 WebCodex 提供任意 shell、网络或文件系统权限给模型：对 Agent 的可用数据是经过本地白名单/Schema/哈希整理的请求。WebCodex 本身有用户授权的项目工具能力，操作者仍需审查插件可能执行的命令。
- `validate_explanation` 防止模型凭空添加证据、用控制器证据证明机械改造或冒充真实实验；质量/惯量变化只能说明指定参数化模型的计算结果，不说明真实四足训练改善。
- 用户编辑 CAD 版本之后，旧建模请求与预览不能被自动应用；源 URDF 或 D02 报告更新后，客户端会比较原文件 SHA，标记历史请求已过期。旧模型回答只解释先前不可变快照，若要分析最新来源必须新建网页请求。确认模型是独立的人为操作。
- 机器可校验文件哈希与提案结构，**不能密码学证明提交回复一定来自某个网页模型**；D03 验收是本次 ChatGPT 网页会话经 WebCodex 的受控实际示例，不代表任意时候可无人值守调用。
- 软件运行需要用户打开网页对话处理任务；不会消耗 Codex CLI 额度，但也不承诺 ChatGPT 消息无限量。

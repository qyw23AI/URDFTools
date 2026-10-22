# 本地 CLI 与 MCP 使用

在项目根目录使用项目 Python 环境，并显式设定只允许访问的工作区：

```bash
PYTHONPATH=python .tools/model-venv/bin/python -m urdftools tool \
  --workspace /绝对路径/工作区 --name inspect_step_conversion \
  --arguments '{"source":"model.step"}'
```

MCP stdio 客户端的启动命令为 `PYTHONPATH=python .tools/model-venv/bin/python -m urdftools mcp --workspace /绝对路径/工作区`。客户端需要支持 MCP `2025-06-18` 初始化流程；stdout 只写 JSON-RPC 消息。当前工具名为 `import_source`、`preview_model_recipe`、`inspect_step_conversion`、`validate_urdf_package`。运行时可用 `tools/list` 读取参数 schema。模型只能预览 CAD 配方，确认应用需回到桌面建模工作台由用户操作。

`source` 参数是工作区内的相对路径。CLI/MCP 都拒绝工作区外的文件和内部存储目录逃逸。`validate_urdf_package` 做 URDF/物理包结构与 MuJoCo 编译检查，不给出训练表现结论。

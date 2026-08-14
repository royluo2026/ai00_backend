# 跨域项目体检插件

这是一个真实的 Manifest v2 Web Plugin。它通过受控 Mount 调用项目、工艺、数模和仿真能力，用精确的 `craft_commit_ref` 与 `model_snapshot_hash` 判断仿真是否基于当前受控输入，并使用插件命名空间存储最近 20 次摘要。

插件不访问 Cookie、数据库、内部 REST、OIS、Electron IPC 或密钥。使用 SDK 构建工具生成发布包：

```powershell
python ../../tools/build_release.py . --output-dir dist
python ../../tools/build_release.py . --output-dir dist --version 1.1.0
```

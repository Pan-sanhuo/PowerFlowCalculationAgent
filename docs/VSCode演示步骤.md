# VS Code 演示步骤

## 1. 打开项目

使用 VS Code 打开解压后的整个文件夹。

## 2. 安装环境

按 `Ctrl+Shift+P`：

```text
Tasks: Run Task
→ 1. 安装运行环境
```

## 3. 运行自动测试

```text
Tasks: Run Task
→ 3. 运行自动测试
```

预期显示所有测试通过。

## 4. 运行完整演示

```text
Tasks: Run Task
→ 2. 运行完整演示
```

依次展示：

1. IEEE 9 节点正常潮流；
2. 缺少 REF、异常初值的自动检查与修复；
3. PV 无功越限、PV→PQ、算法与运行方式搜索。

## 5. 打开结果

在 VS Code 左侧资源管理器打开：

```text
runs/demo_case9/report.md
runs/demo_repairable/report.md
runs/demo_q_limit/report.md
```

重点展示：

- 原始数据检查；
- 每次求解算法；
- Q 限额事件；
- 自动修复动作；
- 雅可比矩阵数值诊断；
- 最终工程可行状态；
- 导出的 `final_feasible_case.py`。

## 6. 展示 DeepSeek 或 Kimi

DeepSeek：

```powershell
$env:DEEPSEEK_API_KEY="你的Key"
.\.venv\Scripts\python.exe .\examples\demo_vscode.py
```

Kimi：

```powershell
$env:KIMI_API_KEY="你的Key"
.\.venv\Scripts\python.exe .\examples\demo_vscode.py
```

不要在屏幕上展示完整 API Key。

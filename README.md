# 电力系统潮流计算智能体（PYPOWER + DeepSeek/Kimi + Streamlit）

这是一个带有人机交互界面的潮流计算智能体。程序以 PYPOWER 为确定性计算核心，以 Streamlit 提供图形化交互界面，完成：

1. 读取 MATPOWER/PYPOWER 风格数据并执行潮流计算；
2. 检查原始数据、节点类型、孤岛、机组限额、支路参数和工程约束；
3. 识别 PV/REF 发电机无功越限，并按 Q 限额执行 PV→PQ 处理；
4. 对不收敛或不可行算例尝试平坦启动、算法切换、机组再调度和基准负荷搜索；
5. 可选调用 DeepSeek、Kimi 或其他 OpenAI-compatible 模型分析数据、过程和结果；
6. 生成 Markdown 报告、JSON 报告和可复算的 Python 算例；
7. 通过 Web 界面完成算例选择、参数配置、运行控制、过程查看与结果展示。

## 二次开发说明

本项目是基于原有命令行版潮流计算智能体进行的**二次开发**，二次开发及维护者为 [Pan-sanhuo](https://github.com/Pan-sanhuo)。

本次二次开发主要增加和优化了：

- 基于 Streamlit 的人机交互界面；
- 对话式操作区域与持久化交互体验；
- 算例、求解器和大模型参数的可视化配置；
- 计算过程、诊断信息和结果报告的页面展示；
- Windows 一键安装和一键启动脚本。

原始项目及第三方依赖的版权仍归各自作者所有，并遵循其原有许可证。本仓库未附带独立许可证时，不代表自动授予额外的复制、分发或商业使用权。

## 一、图形界面快速开始

### 1. 安装环境

双击：

```text
一键安装环境.bat
```

随后安装图形界面依赖：

```text
安装图形界面依赖.bat
```

### 2. 启动人机交互界面

双击：

```text
启动潮流智能体界面.bat
```

也可以在 PowerShell 中运行：

```powershell
.\.venv\Scripts\python.exe -m streamlit run web_ui.py
```

浏览器通常会自动打开 `http://localhost:8501`。

## 二、VS Code 一键运行

### 1. 准备软件

- Python 3.10～3.12
- VS Code
- VS Code 的 Microsoft Python 扩展

### 2. 打开项目

在 VS Code 中选择“文件 → 打开文件夹”，打开本项目根目录。

### 3. 安装环境

按 `Ctrl+Shift+P`，选择 `Tasks: Run Task`，运行：

```text
1. 安装运行环境
```

脚本会创建 `.venv` 并安装与 PYPOWER 兼容的 NumPy/SciPy 版本。

### 4. 运行演示

再次选择 `Tasks: Run Task`，运行：

```text
2. 运行完整演示
```

也可以按 `F5`，选择：

```text
运行潮流智能体完整演示
```

演示结果位于 `runs` 目录。

## 三、手动命令

```powershell
.\.venv\Scripts\python.exe -m pfagent doctor
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pfagent inspect .\examples\case3_bad_data.py
.\.venv\Scripts\python.exe -m pfagent run .\examples\case9_demo.py --engine pypower
.\.venv\Scripts\python.exe -m pfagent run .\examples\case3_q_limit.py --engine pypower --max-rounds 20
```

## 四、演示算例

- `case9_demo.py`：标准 IEEE 9 节点算例，展示正常潮流。
- `case3_repairable.py`：缺少 REF 且初值异常，展示数据检查和修复。
- `case3_q_limit.py`：PV 节点 Q 上限很紧，展示 Q 越限、PV→PQ 和可行方案搜索。
- `case3_bad_data.py`：包含多种错误且物理能力不足，展示“数据修复后仍可能无解”。

## 五、DeepSeek

API Key 不要写入代码。在 VS Code PowerShell 终端中设置：

```powershell
$env:DEEPSEEK_API_KEY="你的API Key"
```

然后运行：

```powershell
.\.venv\Scripts\python.exe -m pfagent run .\examples\case3_q_limit.py `
  --engine pypower `
  --llm-provider deepseek `
  --max-rounds 20 `
  --out .\runs\deepseek_q_limit
```

## 六、Kimi

```powershell
$env:KIMI_API_KEY="你的API Key"
.\.venv\Scripts\python.exe -m pfagent run .\examples\case3_q_limit.py `
  --engine pypower `
  --llm-provider kimi `
  --max-rounds 20 `
  --out .\runs\kimi_q_limit
```

如果服务商更新了模型名称，可增加：

```text
--llm-model 当前可用模型名
```

## 七、代码结构

```text
demo_vscode.py          VS Code 完整演示入口
web_ui.py               Streamlit 人机交互界面
examples/               潮流算例
pfagent/agent.py        智能体闭环控制
pfagent/caseio.py       数据读取与导出
pfagent/validators.py   数据和工程约束检查
pfagent/solvers.py      PYPOWER/MATPOWER 求解器与雅可比诊断
pfagent/repairs.py      自动修复动作
pfagent/llm.py          DeepSeek/Kimi 接口
pfagent/reporting.py    Markdown/JSON 报告
tests/                  自动测试
.vscode/                VS Code 任务和调试配置
.streamlit/             Streamlit 配置
```

## 八、结果状态

程序严格区分：

- `success=True`：求解器收敛，且没有电压、线路或阻断性 Q 越限；
- `solver_converged=True`：潮流方程数值收敛，但不一定工程可行。

只有工程可行时才输出：

```text
final_feasible_case.py
```

若只是数值收敛但存在越限，则输出：

```text
last_converged_but_infeasible_case.py
```

## 九、安全说明

- 不要把 DeepSeek、Kimi 等服务的 API Key 写入代码或提交到仓库；
- `.venv/`、`runs/`、缓存、界面会话数据和本地密钥文件均不应提交；
- API Key 仅通过环境变量或界面会话临时输入。

## 十、答辩时的核心表述

大语言模型不替代潮流求解器。PYPOWER 负责数值求解，规则模块负责确定性校验，LLM 根据结构化数据、工程越限和雅可比数值诊断模仿工程师提出解释与候选措施。所有候选措施必须重新通过 PYPOWER 计算和工程约束复核后，才能被判定为可行运行方式。

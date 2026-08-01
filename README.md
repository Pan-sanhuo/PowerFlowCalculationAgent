# 电力系统潮流计算智能体

一个面向学习、演示和数据诊断的电力系统潮流计算项目。它以 PYPOWER 为数值求解核心，提供规则化的数据检查、自动修复、大模型辅助诊断，以及 Streamlit 人机交互界面。

## 项目能力

- 执行 MATPOWER / PYPOWER 风格算例的交流潮流计算；
- 检查节点类型、孤岛、机组无功限额、支路参数和工程约束；
- 对不可行算例尝试平坦启动、算法切换、机组再调度与负荷搜索；
- 支持 DeepSeek、Kimi 等 OpenAI-compatible 模型生成诊断与修复建议；
- 通过 Streamlit 页面配置算例、查看计算过程、历史记录和报告。

## 二次开发说明

本仓库是在原有命令行版潮流计算智能体基础上的二次开发，维护者为 [Pan-sanhuo](https://github.com/Pan-sanhuo)。本次开发增加了 Streamlit 人机交互界面、运行记录管理、可视化参数配置与 Windows 一键启动脚本。

原始项目及第三方依赖的版权仍归各自作者所有，并遵循其原有许可证；本仓库未附带独立许可证时，不代表自动授予额外的复制、分发或商业使用权。

## 目录结构

```text
.
├─ src/pfagent/          # 核心智能体包：求解、诊断、修复、报告、LLM 接口
├─ apps/streamlit/       # Streamlit 人机交互界面
├─ examples/             # 可运行的潮流算例和完整演示入口
├─ tests/                # 自动测试
├─ scripts/              # 环境安装脚本与 Windows 启动脚本
├─ docs/                 # 演示步骤、任务说明和修改说明
├─ .streamlit/           # Streamlit 配置
├─ pyproject.toml        # Python 打包与命令行入口配置
├─ requirements.txt      # 核心依赖
└─ requirements-ui.txt   # 图形界面依赖
```

## 快速开始

### Windows 图形界面

1. 进入 `scripts/windows/`，双击 `一键安装环境.bat`。
2. 双击 `安装图形界面依赖.bat`。
3. 双击 `启动潮流智能体界面.bat`。

启动后浏览器通常会打开 `http://localhost:8501`。

### 命令行与测试

```powershell
.\.venv\Scripts\python.exe -m pfagent doctor
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pfagent inspect .\examples\case3_bad_data.py
.\.venv\Scripts\python.exe -m pfagent run .\examples\case9_demo.py --engine pypower
```

完整演示入口位于 `examples/demo_vscode.py`。

## 算例

- `case9_demo.py`：标准 IEEE 9 节点潮流；
- `case3_repairable.py`：缺少 REF 节点且初值异常的可修复算例；
- `case3_q_limit.py`：PV 节点无功越限与 PV→PQ 切换；
- `case3_bad_data.py`：包含多种数据错误的诊断算例。

## 安全提示

- 不要提交 `.env`、真实 API Key、`.venv/`、`runs/` 或缓存文件；
- DeepSeek / Kimi 密钥应通过环境变量或界面会话临时输入；
- 只有数值收敛且满足工程约束的结果才会被标记为可行方案。

更多操作说明请查看 [docs](docs/) 目录。

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import streamlit as st

from pfagent.caseio import write_pypower_case
from pfagent.defaults import DEFAULT_MATPOWER_PATH, MATPOWER_BUILTIN_CASES, resolve_matpower_case
from pfagent.llm import LLMClient, LLMConfig


ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "runs"
UPLOAD_DIR = RUNS_DIR / "_ui_uploads"
GENERATED_CASE_DIR = RUNS_DIR / "_ui_builtin_cases"
CHAT_HISTORY_PATH = RUNS_DIR / "_chat_history.json"

PROJECT_EXAMPLES = {
    "项目案例：IEEE 9节点演示": ROOT / "examples" / "case9_demo.py",
    "项目案例：3节点可修复数据": ROOT / "examples" / "case3_repairable.py",
    "项目案例：3节点PV无功越限": ROOT / "examples" / "case3_q_limit.py",
    "项目案例：3节点坏数据": ROOT / "examples" / "case3_bad_data.py",
    "项目案例：DeepSeek修正后坏数据": ROOT / "examples" / "case3_bad_data_deepseek_fixed.py",
}

PYPOWER_STANDARD_CASES = [
    "case4gs",
    "case6ww",
    "case9",
    "case14",
    "case24_ieee_rts",
    "case30",
    "case30Q",
    "case30pwl",
    "case39",
    "case57",
    "case118",
    "case300",
]

ENGINE_LABELS = {"pypower": "pypower", "MATPOWER": "matpower"}
LLM_PROVIDER_IDS = {"关闭，只使用规则": "off", "DeepSeek": "deepseek", "Kimi/Moonshot": "kimi"}
LLM_STAGE_LABELS = {
    "data_inspection": "原始数据复核",
    "repair_proposal": "修复策略建议",
    "result_diagnosis": "结果诊断总结",
}


st.set_page_config(
    page_title="潮流计算智能体",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .stApp { background: #f5f8fb; color: #17263a; }
        .block-container { max-width: 1500px; padding-top: 1.6rem; }
        .hero {
            background: linear-gradient(120deg, #071d33, #123e63);
            color: white; border-radius: 14px; padding: 34px 34px;
            margin: 8px 0 20px; box-shadow: 0 12px 30px rgba(7,29,51,.18);
        }
        .hero h1 { margin: 0; font-size: 36px; line-height: 1.25; }
        .hero p { margin: 0; color: #c9d9e8; }
        .badge {
            display: inline-block; padding: 5px 10px; border-radius: 999px;
            margin: 14px 8px 0 0; font-size: 12px;
            background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.18);
        }
        .flow {
            display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 9px;
            margin-bottom: 18px;
        }
        .step {
            background: white; border: 1px solid #dbe5ef; border-radius: 10px;
            padding: 12px 13px; min-height: 76px;
        }
        .step b { color: #14263a; }
        .step span { color: #63758b; font-size: 12px; }
        .metric {
            background: white; border: 1px solid #dbe5ef; border-left: 5px solid #05a6c7;
            border-radius: 10px; padding: 16px 18px; min-height: 105px;
        }
        .metric.orange { border-left-color: #ff8b22; }
        .metric.green { border-left-color: #25b485; }
        .metric.red { border-left-color: #d94f4f; }
        .metric .label { color: #65758a; font-size: 13px; font-weight: 650; }
        .metric .value { color: #16263a; font-size: 28px; font-weight: 850; margin-top: 5px; }
        .metric .note { color: #8290a0; font-size: 12px; margin-top: 5px; }
        .panel {
            background: white; border: 1px solid #dbe5ef; border-radius: 10px;
            padding: 15px 17px; margin: 10px 0;
        }
        .panel-title { font-size: 16px; font-weight: 800; color: #14263a; margin-bottom: 6px; }
        .panel-note { color: #65758a; font-size: 13px; line-height: 1.55; }
        .pill {
            display: inline-block; padding: 4px 9px; border-radius: 999px;
            font-size: 12px; font-weight: 750; margin-right: 6px; margin-bottom: 6px;
            background: #e8f6fb; color: #067b95;
        }
        .pill.ok { background: #e7f8f1; color: #08785c; }
        .pill.warn { background: #fff1df; color: #a65b0a; }
        .pill.bad { background: #fdeaea; color: #b53434; }
        @media (max-width: 900px) { .flow { grid-template-columns: 1fr; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st.markdown(
        """
        <div class="hero">
          <h1>电力系统潮流计算智能体</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric(label: str, value: str, note: str = "", tone: str = "") -> None:
    st.markdown(
        f"""
        <div class="metric {tone}">
          <div class="label">{label}</div>
          <div class="value">{value}</div>
          <div class="note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def info_panel(title: str, body: str, pills: list[tuple[str, str]] | None = None) -> None:
    pill_html = ""
    for text, tone in pills or []:
        pill_html += f'<span class="pill {tone}">{text}</span>'
    st.markdown(
        f"""
        <div class="panel">
          <div class="panel-title">{title}</div>
          <div>{pill_html}</div>
          <div class="panel-note">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def dataframe_from(items: list[dict[str, Any]]) -> None:
    if not items:
        st.info("暂无记录")
        return
    st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)


def save_upload(uploaded: Any) -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = UPLOAD_DIR / f"{stamp}_{Path(uploaded.name).name}"
    out.write_bytes(uploaded.getbuffer())
    return out


def create_pypower_standard_case(case_name: str) -> Path:
    from pypower import api as pypower_api

    if not hasattr(pypower_api, case_name):
        raise ValueError(f"PYPOWER中未找到标准算例：{case_name}")
    GENERATED_CASE_DIR.mkdir(parents=True, exist_ok=True)
    ppc = getattr(pypower_api, case_name)()
    return write_pypower_case(ppc, GENERATED_CASE_DIR / f"{case_name}.py", case_name)


def load_file_text(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def load_json(path: Path | None) -> dict[str, Any] | None:
    if not path or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def ensure_job_state() -> None:
    st.session_state.setdefault("running_job", None)
    st.session_state.setdefault("last_finished_out_dir", None)


def process_status(job: dict[str, Any] | None) -> str:
    if not job:
        return "idle"
    proc = job.get("process")
    if proc is None:
        return "unknown"
    return "running" if proc.poll() is None else "finished"


def start_background_job(controls: dict[str, Any]) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    case_path = Path(controls["case_path"])
    out_dir = RUNS_DIR / f"ui_{case_path.stem}_{controls['engine']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "console.log"

    command = [
        sys.executable,
        "-m",
        "pfagent",
        "run",
        str(case_path),
        "--engine",
        controls["engine"],
        "--max-rounds",
        str(controls["max_rounds"]),
        "--out",
        str(out_dir),
    ]
    if not controls["auto_repair"]:
        command.append("--no-auto-repair")
    command.extend(["--llm-provider", controls["llm_provider"]])
    if controls["llm_model"]:
        command.extend(["--llm-model", controls["llm_model"]])
    if controls["llm_base_url"]:
        command.extend(["--llm-base-url", controls["llm_base_url"]])

    process_env = os.environ.copy()
    if controls["llm_api_key"]:
        if controls["llm_provider"] == "deepseek":
            process_env["DEEPSEEK_API_KEY"] = controls["llm_api_key"]
        elif controls["llm_provider"] == "kimi":
            process_env["KIMI_API_KEY"] = controls["llm_api_key"]

    log_handle = log_path.open("w", encoding="utf-8", errors="ignore")
    proc = subprocess.Popen(
        command,
        cwd=str(ROOT),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        env=process_env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP") else 0,
    )
    log_handle.close()

    st.session_state.running_job = {
        "process": proc,
        "pid": proc.pid,
        "out_dir": str(out_dir),
        "log_path": str(log_path),
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "case_path": str(case_path),
        "engine": controls["engine_label"],
        "command": " ".join(command),
    }
    st.session_state.last_finished_out_dir = None


def cancel_background_job() -> None:
    job = st.session_state.get("running_job")
    if not job:
        return
    proc = job.get("process")
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    out_dir = Path(job["out_dir"])
    (out_dir / "cancelled.txt").write_text("用户在界面中取消了本次计算。\n", encoding="utf-8")
    st.session_state.last_finished_out_dir = str(out_dir)
    st.session_state.running_job = None


def finalize_finished_job() -> None:
    job = st.session_state.get("running_job")
    if job and process_status(job) == "finished":
        st.session_state.last_finished_out_dir = job["out_dir"]
        st.session_state.running_job = None


def run_controls() -> dict[str, Any]:
    with st.sidebar:
        st.subheader("运行控制")
        engine_label = st.radio("求解器", ["pypower", "MATPOWER"], horizontal=True, index=0)
        engine = ENGINE_LABELS[engine_label]

        source = st.radio(
            "算例来源",
            ["项目演示算例", "PYPOWER标准案例", "MATPOWER标准案例", "上传算例文件"],
            index=0,
        )

        case_path: Path | None = None
        case_desc = ""
        if source == "项目演示算例":
            selected = st.selectbox("选择项目演示算例", list(PROJECT_EXAMPLES))
            case_path = PROJECT_EXAMPLES[selected]
            case_desc = selected
        elif source == "PYPOWER标准案例":
            selected = st.selectbox("选择PYPOWER标准案例", PYPOWER_STANDARD_CASES, index=2)
            case_path = create_pypower_standard_case(selected)
            case_desc = f"PYPOWER标准案例：{selected}"
        elif source == "MATPOWER标准案例":
            selected = st.selectbox("选择MATPOWER标准案例", MATPOWER_BUILTIN_CASES, index=0)
            case_path = resolve_matpower_case(selected)
            case_desc = f"MATPOWER标准案例：{selected}"
            st.info(f"MATPOWER已内嵌：{DEFAULT_MATPOWER_PATH}")
        else:
            uploaded = st.file_uploader("上传算例文件", type=["py", "m", "mat", "json"])
            if uploaded is not None:
                case_path = save_upload(uploaded)
                case_desc = f"上传文件：{uploaded.name}"

        st.caption(f"当前求解器：{engine_label}")
        if case_desc:
            st.caption(f"当前算例：{case_desc}")

        auto_repair = st.toggle("启用自动诊断与修复", value=True)
        max_rounds = st.slider("最大尝试轮数", 1, 40, 20)

        st.subheader("大模型")
        llm_labels = list(LLM_PROVIDER_IDS)
        llm_label = st.selectbox("LLM供应商", llm_labels, index=llm_labels.index("DeepSeek"))
        llm_provider = LLM_PROVIDER_IDS[llm_label]
        llm_model = ""
        llm_api_key = ""
        llm_base_url = ""

        run_clicked = st.button(
            "开始运行潮流智能体",
            type="primary",
            use_container_width=True,
            disabled=process_status(st.session_state.get("running_job")) == "running",
        )

    return {
        "case_path": case_path,
        "engine": engine,
        "engine_label": engine_label,
        "auto_repair": auto_repair,
        "max_rounds": max_rounds,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_api_key": llm_api_key,
        "llm_base_url": llm_base_url,
        "run_clicked": run_clicked,
        "source": source,
    }


def render_job_control() -> None:
    finalize_finished_job()
    job = st.session_state.get("running_job")
    status = process_status(job)

    if status == "running":
        info_panel(
            "当前计算任务正在运行",
            f"进程 PID：{job['pid']}；开始时间：{job['started_at']}；输出目录：{job['out_dir']}",
            [("运行中", "warn"), (job["engine"], "ok")],
        )
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("刷新计算状态", use_container_width=True):
                st.rerun()
        with c2:
            if st.button("取消计算", type="secondary", use_container_width=True):
                cancel_background_job()
                st.warning("已请求取消当前计算。")
                st.rerun()
        log_text = load_file_text(Path(job["log_path"]))
        if log_text:
            with st.expander("查看实时控制台日志", expanded=False):
                st.code(log_text[-5000:], language="text")
    elif st.session_state.get("last_finished_out_dir"):
        out_dir = Path(st.session_state.last_finished_out_dir)
        if (out_dir / "report.json").exists():
            st.success(f"上一次计算已完成：{out_dir}")
        elif (out_dir / "cancelled.txt").exists():
            st.warning(f"上一次计算已取消：{out_dir}")
        elif (out_dir / "console.log").exists():
            st.warning(f"上一次计算结束，但未生成 report.json：{out_dir}")


def load_history_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not RUNS_DIR.exists():
        return records

    for run_dir in RUNS_DIR.iterdir():
        if not run_dir.is_dir() or run_dir.name.startswith("_"):
            continue
        report_path = run_dir / "report.json"
        if not report_path.exists() and (run_dir / "verification" / "report.json").exists():
            report_path = run_dir / "verification" / "report.json"
        data = load_json(report_path)
        if not data:
            continue
        attempts = data.get("attempts", [])
        last_attempt = attempts[-1] if attempts else {}
        run_time = datetime.fromtimestamp(run_dir.stat().st_mtime)
        records.append(
            {
                "显示名称": f"{run_dir.name} | {'可行' if data.get('success') else '未完全可行'}",
                "目录名": run_dir.name,
                "输出目录": str(run_dir),
                "报告JSON": str(report_path),
                "算例": Path(str(data.get("case_path", ""))).name,
                "工程可行": bool(data.get("success")),
                "收敛": bool(data.get("solver_converged", last_attempt.get("success"))),
                "尝试次数": len(attempts),
                "运行时间": f"{run_time.year}年{run_time.month}月{run_time.day}日 {run_time:%H:%M}",
                "最后修改时间": run_dir.stat().st_mtime,
            }
        )
    return sorted(records, key=lambda item: item["最后修改时间"], reverse=True)


def delete_history_record(record: dict[str, Any]) -> None:
    path = Path(record["输出目录"]).resolve()
    runs_root = RUNS_DIR.resolve()
    if runs_root not in path.parents:
        raise ValueError("拒绝删除 runs 目录之外的文件夹。")
    if path == runs_root or path.name.startswith("_"):
        raise ValueError("拒绝删除系统目录。")
    shutil.rmtree(path)


def compact_text(value: Any, limit: int = 220) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "..."


def render_result_summary(data: dict[str, Any]) -> None:
    attempts = data.get("attempts", [])
    repairs = data.get("repairs", [])
    last_attempt = attempts[-1] if attempts else {}
    q_events = sum(len(item.get("q_limit_events", [])) for item in attempts)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric("工程可行", "是" if data.get("success") else "否", "收敛且无工程约束越限", "green" if data.get("success") else "orange")
    with c2:
        converged = data.get("solver_converged", last_attempt.get("success"))
        metric("求解器收敛", "是" if converged else "否", f"最后一次尝试：{last_attempt.get('name', '-')}")
    with c3:
        metric("计算尝试次数", str(len(attempts)), "自动修复过程会保留每次尝试")
    with c4:
        metric("修复动作 / Q事件", f"{len(repairs)} / {q_events}", "记录PV→PQ、算法切换、负荷缩放等", "orange")


def render_llm_stage(stage_key: str, payload: Any) -> None:
    label = LLM_STAGE_LABELS.get(stage_key, stage_key)
    if not isinstance(payload, dict):
        info_panel(label, compact_text(payload), [("原始文本", "warn")])
        return

    enabled = bool(payload.get("enabled"))
    error = payload.get("error")
    parsed = payload.get("parsed")
    content = payload.get("content")
    message = payload.get("message")

    if error:
        status = [("调用失败", "bad")]
        body = compact_text(error, 420)
    elif not enabled:
        status = [("规则模式", "warn")]
        body = compact_text(message or "未启用大模型，系统使用规则诊断。", 420)
    elif parsed:
        status = [("已调用LLM", "ok"), ("结构化解析成功", "ok")]
        body = "大模型返回了可解析的结构化结果，下面按字段展开展示。"
    else:
        status = [("已调用LLM", "ok"), ("仅原文输出", "warn")]
        body = compact_text(content or message or "LLM已返回结果。", 420)

    info_panel(label, body, status)
    if isinstance(parsed, dict):
        render_parsed_llm(parsed)
    elif parsed:
        st.write(parsed)

    if content:
        with st.expander(f"{label}：查看LLM原文", expanded=False):
            st.markdown(str(content))


def render_parsed_llm(parsed: dict[str, Any]) -> None:
    summary_items = []
    table_items = []
    other_items = {}
    for key, value in parsed.items():
        if isinstance(value, list):
            if value and all(isinstance(item, dict) for item in value):
                table_items.append((key, value))
            else:
                summary_items.append({"字段": key, "内容": "；".join(map(str, value[:8]))})
        elif isinstance(value, dict):
            other_items[key] = value
        else:
            summary_items.append({"字段": key, "内容": compact_text(value, 260)})

    if summary_items:
        st.markdown("##### 关键结论")
        dataframe_from(summary_items)
    for key, value in table_items:
        st.markdown(f"##### {key}")
        dataframe_from(value)
    for key, value in other_items.items():
        with st.expander(f"查看 {key} 详情", expanded=False):
            st.json(value)


def render_llm_view(data: dict[str, Any]) -> None:
    sections = data.get("llm_sections") or {}
    if not sections:
        st.info("本次运行没有LLM诊断记录。")
        return

    rows = []
    for key, payload in sections.items():
        if isinstance(payload, dict):
            if payload.get("error"):
                status = "失败"
            elif payload.get("enabled") is False:
                status = "规则模式"
            elif payload.get("parsed"):
                status = "已解析"
            else:
                status = "已返回原文"
            brief = payload.get("message") or payload.get("error") or compact_text(payload.get("parsed") or payload.get("content"), 120)
        else:
            status = "文本"
            brief = compact_text(payload, 120)
        rows.append({"阶段": LLM_STAGE_LABELS.get(key, key), "状态": status, "摘要": brief})

    st.markdown("#### LLM诊断总览")
    dataframe_from(rows)
    st.markdown("#### 分阶段查看")
    for key, payload in sections.items():
        render_llm_stage(key, payload)


def split_markdown_sections(markdown_text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title = "报告开头"
    current_lines: list[str] = []
    for line in markdown_text.splitlines():
        if line.startswith("#"):
            if current_lines:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = line.lstrip("#").strip() or "未命名章节"
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_title, "\n".join(current_lines).strip()))
    return [(title, body) for title, body in sections if body]


def render_report_preview(data: dict[str, Any]) -> None:
    report_path = Path(data["final_report_path"]) if data.get("final_report_path") else None
    json_path = Path(data["final_json_path"]) if data.get("final_json_path") else None
    case_path = Path(data["final_case_path"]) if data.get("final_case_path") else None
    attempts = data.get("attempts", [])
    last_attempt = attempts[-1] if attempts else {}
    converged = data.get("solver_converged", last_attempt.get("success"))

    info_panel(
        "报告阅读摘要",
        "这里先展示最终结论和输出文件，完整报告按章节折叠在下方，便于答辩或检查时快速定位。",
        [
            ("工程可行" if data.get("success") else "未完全可行", "ok" if data.get("success") else "warn"),
            ("求解器收敛" if converged else "求解器未收敛", "ok" if converged else "bad"),
        ],
    )

    files = []
    for label, path in [("Markdown报告", report_path), ("JSON结构化结果", json_path), ("最终/最后算例", case_path)]:
        if path:
            files.append({"文件类型": label, "路径": str(path), "是否存在": path.exists()})
    dataframe_from(files)

    c1, c2, c3 = st.columns(3)
    for col, label, path in [(c1, "下载Markdown报告", report_path), (c2, "下载JSON结果", json_path), (c3, "下载最终算例", case_path)]:
        with col:
            if path and path.exists():
                st.download_button(label, data=path.read_bytes(), file_name=path.name, use_container_width=True)

    if not report_path or not report_path.exists():
        st.info("暂无Markdown报告文件。")
        return

    markdown_text = load_file_text(report_path)
    st.markdown("#### 报告分段预览")
    for index, (title, body) in enumerate(split_markdown_sections(markdown_text), start=1):
        with st.expander(f"{index}. {title}", expanded=index <= 2):
            st.markdown(body)
    with st.expander("查看完整Markdown原文", expanded=False):
        st.code(markdown_text, language="markdown")


def render_report_data(data: dict[str, Any]) -> None:
    render_result_summary(data)
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["计算尝试", "数据检查", "修复动作", "LLM诊断", "报告与文件"])
    with tab1:
        rows = []
        for attempt in data.get("attempts", []):
            rows.append(
                {
                    "尝试名称": attempt.get("name"),
                    "求解器": attempt.get("engine"),
                    "算法": (attempt.get("options") or {}).get("pf_alg_name"),
                    "收敛": attempt.get("success"),
                    "工程可行": attempt.get("feasible"),
                    "耗时/s": attempt.get("elapsed_s"),
                    "越限数": len(attempt.get("violations", [])),
                    "Q限额事件": len(attempt.get("q_limit_events", [])),
                    "错误": attempt.get("error") or "",
                }
            )
        dataframe_from(rows)
    with tab2:
        dataframe_from(data.get("validation", []))
    with tab3:
        dataframe_from(data.get("repairs", []))
    with tab4:
        render_llm_view(data)
    with tab5:
        render_report_preview(data)


def render_history_manager() -> None:
    title_col, refresh_col = st.columns([5, 1])
    with title_col:
        st.markdown("### 历史计算记录")
    with refresh_col:
        if st.button("刷新历史记录", use_container_width=True):
            st.rerun()
    records = load_history_records()
    if not records:
        st.info("暂无历史记录。运行一次计算后，这里会自动出现记录。")
        return

    st.session_state.setdefault("history_editor_version", 0)

    table_rows = [
        {
            "记录ID": item["目录名"],
            "选择": False,
            "算例": item["算例"],
            "工程可行": item["工程可行"],
            "收敛": item["收敛"],
            "尝试次数": item["尝试次数"],
            "运行时间": item["运行时间"],
        }
        for item in records
    ]
    editor_key = f"history_record_selector_{st.session_state.history_editor_version}"
    edited_rows = st.data_editor(
        pd.DataFrame(table_rows),
        use_container_width=True,
        disabled=["算例", "工程可行", "收敛", "尝试次数", "运行时间"],
        column_config={
            "记录ID": None,
            "选择": st.column_config.CheckboxColumn(
                "选择",
                help="勾选一条或多条历史记录后，可以批量删除。",
                width="small",
                alignment="center",
                default=False,
            ),
            "运行时间": st.column_config.TextColumn(
                "运行时间",
                width="medium",
                alignment="center",
            ),
        },
        key=editor_key,
    )
    selected_dirs = set(
        edited_rows.loc[edited_rows["选择"].astype(bool), "记录ID"].astype(str).tolist()
        if "记录ID" in edited_rows.columns
        else []
    )
    selected_records = [item for item in records if item["目录名"] in selected_dirs]

    selected_label = st.selectbox("选择要查看的历史记录", [item["显示名称"] for item in records])
    selected = next(item for item in records if item["显示名称"] == selected_label)
    c1, c2 = st.columns([1, 1])
    with c1:
        open_clicked = st.button("打开该历史记录", use_container_width=True)
    with c2:
        delete_clicked = st.button(
            f"删除选中历史记录（{len(selected_records)}）",
            disabled=not selected_records,
            use_container_width=True,
        )

    if delete_clicked:
        failed: list[str] = []
        for record in selected_records:
            try:
                delete_history_record(record)
            except Exception as exc:
                failed.append(f"{record['目录名']}：{type(exc).__name__}: {exc}")
        if failed:
            st.error("部分历史记录删除失败：\n" + "\n".join(failed))
        else:
            st.session_state.history_editor_version += 1
            st.success(f"已删除 {len(selected_records)} 条历史记录。")
            st.rerun()

    if open_clicked:
        data = load_json(Path(selected["报告JSON"]))
        if data:
            st.markdown(f"#### 正在查看：{selected['目录名']}")
            render_report_data(data)
        else:
            st.error("无法读取该历史记录的 report.json。")


def _render_recent_result_if_available() -> None:
    finished_dir = Path(st.session_state.last_finished_out_dir) if st.session_state.get("last_finished_out_dir") else None
    if finished_dir and (finished_dir / "report.json").exists():
        data = load_json(finished_dir / "report.json")
        if data:
            st.markdown("### 最近一次计算结果")
            render_report_data(data)


def _render_live_area_body() -> None:
    render_job_control()
    _render_recent_result_if_available()


if hasattr(st, "fragment"):
    render_live_area = st.fragment(run_every=2)(_render_live_area_body)
else:
    render_live_area = _render_live_area_body


def _latest_report_context() -> dict[str, Any] | None:
    out_dir_text = st.session_state.get("last_finished_out_dir")
    if not out_dir_text:
        return None
    report_path = Path(out_dir_text) / "report.json"
    data = load_json(report_path)
    if not data:
        return None
    attempts = data.get("attempts", [])
    last_attempt = attempts[-1] if attempts else {}
    return {
        "case_path": data.get("case_path"),
        "engineering_feasible": data.get("success"),
        "solver_converged": data.get("solver_converged", last_attempt.get("success")),
        "attempt_count": len(attempts),
        "last_attempt": {
            "name": last_attempt.get("name"),
            "success": last_attempt.get("success"),
            "feasible": last_attempt.get("feasible"),
            "error": last_attempt.get("error"),
            "violations": last_attempt.get("violations", [])[:20],
            "q_limit_events": last_attempt.get("q_limit_events", [])[:20],
        },
        "repairs": data.get("repairs", [])[:20],
    }


def _new_chat_conversation() -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "id": uuid4().hex,
        "title": "新对话",
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }


def load_chat_history() -> dict[str, Any]:
    data = load_json(CHAT_HISTORY_PATH)
    if not isinstance(data, dict) or not isinstance(data.get("conversations"), list):
        return {"version": 1, "conversations": []}

    conversations = []
    for item in data["conversations"]:
        if not isinstance(item, dict) or not item.get("id") or not isinstance(item.get("messages"), list):
            continue
        conversations.append(item)
    return {"version": 1, "conversations": conversations}


def save_chat_history(history: dict[str, Any]) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = CHAT_HISTORY_PATH.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(history, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    temp_path.replace(CHAT_HISTORY_PATH)


def _chat_title(prompt: str) -> str:
    title = " ".join(prompt.split())
    return title if len(title) <= 24 else title[:24] + "…"


def _chat_option_label(conversation: dict[str, Any]) -> str:
    updated_at = str(conversation.get("updated_at", "")).replace("T", " ")
    return f"{conversation.get('title') or '新对话'}　{updated_at[:16]}"


def render_chat(controls: dict[str, Any]) -> None:
    st.subheader("潮流智能问答")
    st.caption("可询问潮流计算原理、算例数据、收敛问题，以及最近一次计算结果。历史对话会自动保存在本机。")
    history = load_chat_history()
    if not history["conversations"]:
        history["conversations"].append(_new_chat_conversation())
        save_chat_history(history)

    conversations_by_id = {item["id"]: item for item in history["conversations"]}
    requested_id = st.session_state.get("chat_conversation_selector")
    current_id = requested_id if requested_id in conversations_by_id else st.session_state.get("current_chat_id")
    if current_id not in conversations_by_id:
        current_id = max(history["conversations"], key=lambda item: item.get("updated_at", ""))["id"]
    st.session_state.current_chat_id = current_id
    conversation = conversations_by_id[current_id]
    messages = conversation["messages"]

    config = LLMConfig.from_env(
        provider=controls["llm_provider"],
        model=controls["llm_model"] or None,
        base_url=controls["llm_base_url"] or None,
        api_key=controls["llm_api_key"] or None,
    )

    if controls["llm_provider"] == "off":
        st.info("请在左侧“大模型”中选择 DeepSeek 或 Kimi。")
    elif not config.enabled:
        env_name = "DEEPSEEK_API_KEY" if controls["llm_provider"] == "deepseek" else "KIMI_API_KEY"
        st.warning(f"未检测到模型密钥，请先设置系统环境变量 {env_name}。")
    else:
        st.caption(f"当前模型：{config.model} · {controls['llm_provider']}")

    messages_window = st.container(height=500, border=True)
    with messages_window:
        if not messages:
            with st.chat_message("assistant"):
                st.markdown("你好，我是潮流计算智能体。你可以直接描述问题，例如：**为什么 PV 节点会转成 PQ 节点？**")
        else:
            for message in messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

    prompt = st.chat_input("输入你的问题，例如：分析最近一次潮流计算为什么没有收敛")

    history_col, new_col, delete_col = st.columns([4, 1, 1])
    with new_col:
        if st.button("新建对话", width="stretch"):
            new_conversation = _new_chat_conversation()
            history["conversations"].append(new_conversation)
            save_chat_history(history)
            st.session_state.current_chat_id = new_conversation["id"]
            st.session_state.chat_conversation_selector = new_conversation["id"]
            st.rerun()
    with delete_col:
        with st.popover("删除对话", width="stretch"):
            st.warning("删除后无法恢复，确定删除当前对话吗？")
            if st.button("确认删除", type="primary", width="stretch"):
                history["conversations"] = [
                    item for item in history["conversations"] if item["id"] != current_id
                ]
                if not history["conversations"]:
                    history["conversations"].append(_new_chat_conversation())
                next_conversation = max(
                    history["conversations"],
                    key=lambda item: item.get("updated_at", ""),
                )
                save_chat_history(history)
                st.session_state.current_chat_id = next_conversation["id"]
                st.session_state.chat_conversation_selector = next_conversation["id"]
                st.rerun()
    with history_col:
        sorted_conversations = sorted(
            history["conversations"],
            key=lambda item: item.get("updated_at", ""),
            reverse=True,
        )
        option_ids = [item["id"] for item in sorted_conversations]
        option_lookup = {item["id"]: item for item in sorted_conversations}
        selected_index = option_ids.index(current_id) if current_id in option_ids else 0
        st.selectbox(
            "历史对话",
            option_ids,
            index=selected_index,
            format_func=lambda item_id: _chat_option_label(option_lookup[item_id]),
            key="chat_conversation_selector",
        )

    if not prompt:
        return

    messages.append({"role": "user", "content": prompt})
    if conversation.get("title") == "新对话":
        conversation["title"] = _chat_title(prompt)
    conversation["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_chat_history(history)
    with messages_window:
        with st.chat_message("user"):
            st.markdown(prompt)

    if not config.enabled:
        answer = "尚未配置可用的大模型。请选择供应商，并设置相应的 API Key 系统环境变量。"
    else:
        system_prompt = (
            "你是电力系统潮流计算智能体，也是耐心、严谨的中文技术助手。"
            "优先回答潮流计算、MATPOWER、PYPOWER、收敛诊断、运行约束和算例数据问题。"
            "回答应先给结论，再解释依据；不确定时明确说明，不得编造计算结果。"
            "若提供了最近一次计算结果上下文，应引用其中的具体事实回答。"
        )
        report_context = _latest_report_context()
        if report_context:
            system_prompt += "\n最近一次潮流计算结果上下文：\n" + json.dumps(
                report_context,
                ensure_ascii=False,
                default=str,
            )
        with messages_window:
            with st.chat_message("assistant"):
                with st.spinner("正在思考..."):
                    result = LLMClient(config).chat_text(
                        messages[-20:],
                        system_prompt=system_prompt,
                    )
                    if result.get("error"):
                        answer = f"模型调用失败：{result['error']}"
                    else:
                        answer = str(result.get("content") or "模型没有返回有效内容，请稍后重试。")
                    st.markdown(answer)
        messages.append({"role": "assistant", "content": answer})
        conversation["updated_at"] = datetime.now().isoformat(timespec="seconds")
        save_chat_history(history)
        return

    with messages_window:
        with st.chat_message("assistant"):
            st.warning(answer)
    messages.append({"role": "assistant", "content": answer})
    conversation["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_chat_history(history)


def main() -> None:
    inject_css()
    ensure_job_state()
    render_header()
    controls = run_controls()

    chat_tab, calculation_tab = st.tabs(["智能问答", "潮流计算与结果"])
    with chat_tab:
        render_chat(controls)

    with calculation_tab:
        if controls["engine"] == "matpower" and not Path(DEFAULT_MATPOWER_PATH).exists():
            st.error(f"MATPOWER默认路径不存在：{DEFAULT_MATPOWER_PATH}")
        else:
            if controls["run_clicked"]:
                if controls["case_path"] is None:
                    st.warning("请先选择或上传一个算例文件。")
                elif not Path(controls["case_path"]).exists():
                    st.error(f"算例文件不存在：{controls['case_path']}")
                else:
                    start_background_job(controls)
                    st.success("计算任务已启动。可以点击“刷新计算状态”查看进度，或点击“取消计算”终止。")
                    st.rerun()

            render_live_area()
            if not st.session_state.get("running_job") and not st.session_state.get("last_finished_out_dir"):
                info_panel(
                    "请输入潮流计算案例",
                    "请在左侧选择算例来源、固定求解器和大模型设置，然后点击“开始运行潮流智能体”。",
                    [],
                )
            st.divider()
            render_history_manager()


if __name__ == "__main__":
    main()

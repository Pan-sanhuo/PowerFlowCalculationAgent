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
    "é¡¹ç›®æ¡ˆä¾‹ï¼šIEEE 9èŠ‚ç‚¹æ¼”ç¤º": ROOT / "examples" / "case9_demo.py",
    "é¡¹ç›®æ¡ˆä¾‹ï¼š3èŠ‚ç‚¹å¯ä¿®å¤æ•°æ®": ROOT / "examples" / "case3_repairable.py",
    "é¡¹ç›®æ¡ˆä¾‹ï¼š3èŠ‚ç‚¹PVæ— åŠŸè¶Šé™": ROOT / "examples" / "case3_q_limit.py",
    "é¡¹ç›®æ¡ˆä¾‹ï¼š3èŠ‚ç‚¹åæ•°æ®": ROOT / "examples" / "case3_bad_data.py",
    "é¡¹ç›®æ¡ˆä¾‹ï¼šDeepSeekä¿®æ­£ååæ•°æ®": ROOT / "examples" / "case3_bad_data_deepseek_fixed.py",
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
LLM_PROVIDER_IDS = {"å…³é—­ï¼Œåªä½¿ç”¨è§„åˆ™": "off", "DeepSeek": "deepseek", "Kimi/Moonshot": "kimi"}
LLM_STAGE_LABELS = {
    "data_inspection": "åŸå§‹æ•°æ®å¤æ ¸",
    "repair_proposal": "ä¿®å¤ç­–ç•¥å»ºè®®",
    "result_diagnosis": "ç»“æœè¯Šæ–­æ€»ç»“",
}


st.set_page_config(
    page_title="æ½®æµè®¡ç®—æ™ºèƒ½ä½“",
    page_icon="âš¡",
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
          <h1>ç”µåŠ›ç³»ç»Ÿæ½®æµè®¡ç®—æ™ºèƒ½ä½“</h1>
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
        st.info("æš‚æ— è®°å½•")
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
        raise ValueError(f"PYPOWERä¸­æœªæ‰¾åˆ°æ ‡å‡†ç®—ä¾‹ï¼š{case_name}")
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
    (out_dir / "cancelled.txt").write_text("ç”¨æˆ·åœ¨ç•Œé¢ä¸­å–æ¶ˆäº†æœ¬æ¬¡è®¡ç®—ã€‚\n", encoding="utf-8")
    st.session_state.last_finished_out_dir = str(out_dir)
    st.session_state.running_job = None


def finalize_finished_job() -> None:
    job = st.session_state.get("running_job")
    if job and process_status(job) == "finished":
        st.session_state.last_finished_out_dir = job["out_dir"]
        st.session_state.running_job = None


def run_controls() -> dict[str, Any]:
    with st.sidebar:
        st.subheader("è¿è¡Œæ§åˆ¶")
        engine_label = st.radio("æ±‚è§£å™¨", ["pypower", "MATPOWER"], horizontal=True, index=0)
        engine = ENGINE_LABELS[engine_label]

        source = st.radio(
            "ç®—ä¾‹æ¥æº",
            ["é¡¹ç›®æ¼”ç¤ºç®—ä¾‹", "PYPOWERæ ‡å‡†æ¡ˆä¾‹", "MATPOWERæ ‡å‡†æ¡ˆä¾‹", "ä¸Šä¼ ç®—ä¾‹æ–‡ä»¶"],
            index=0,
        )

        case_path: Path | None = None
        case_desc = ""
        if source == "é¡¹ç›®æ¼”ç¤ºç®—ä¾‹":
            selected = st.selectbox("é€‰æ‹©é¡¹ç›®æ¼”ç¤ºç®—ä¾‹", list(PROJECT_EXAMPLES))
            case_path = PROJECT_EXAMPLES[selected]
            case_desc = selected
        elif source == "PYPOWERæ ‡å‡†æ¡ˆä¾‹":
            selected = st.selectbox("é€‰æ‹©PYPOWERæ ‡å‡†æ¡ˆä¾‹", PYPOWER_STANDARD_CASES, index=2)
            case_path = create_pypower_standard_case(selected)
            case_desc = f"PYPOWERæ ‡å‡†æ¡ˆä¾‹ï¼š{selected}"
        elif source == "MATPOWERæ ‡å‡†æ¡ˆä¾‹":
            selected = st.selectbox("é€‰æ‹©MATPOWERæ ‡å‡†æ¡ˆä¾‹", MATPOWER_BUILTIN_CASES, index=0)
            case_path = resolve_matpower_case(selected)
            case_desc = f"MATPOWERæ ‡å‡†æ¡ˆä¾‹ï¼š{selected}"
            st.info(f"MATPOWERå·²å†…åµŒï¼š{DEFAULT_MATPOWER_PATH}")
        else:
            uploaded = st.file_uploader("ä¸Šä¼ ç®—ä¾‹æ–‡ä»¶", type=["py", "m", "mat", "json"])
            if uploaded is not None:
                case_path = save_upload(uploaded)
                case_desc = f"ä¸Šä¼ æ–‡ä»¶ï¼š{uploaded.name}"

        st.caption(f"å½“å‰æ±‚è§£å™¨ï¼š{engine_label}")
        if case_desc:
            st.caption(f"å½“å‰ç®—ä¾‹ï¼š{case_desc}")

        auto_repair = st.toggle("å¯ç”¨è‡ªåŠ¨è¯Šæ–­ä¸ä¿®å¤", value=True)
        max_rounds = st.slider("æœ€å¤§å°è¯•è½®æ•°", 1, 40, 20)

        st.subheader("å¤§æ¨¡å‹")
        llm_labels = list(LLM_PROVIDER_IDS)
        llm_label = st.selectbox("LLMä¾›åº”å•†", llm_labels, index=llm_labels.index("DeepSeek"))
        llm_provider = LLM_PROVIDER_IDS[llm_label]
        llm_model = ""
        llm_api_key = ""
        llm_base_url = ""

        run_clicked = st.button(
            "å¼€å§‹è¿è¡Œæ½®æµæ™ºèƒ½ä½“",
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
            "å½“å‰è®¡ç®—ä»»åŠ¡æ­£åœ¨è¿è¡Œ",
            f"è¿›ç¨‹ PIDï¼š{job['pid']}ï¼›å¼€å§‹æ—¶é—´ï¼š{job['started_at']}ï¼›è¾“å‡ºç›®å½•ï¼š{job['out_dir']}",
            [("è¿è¡Œä¸­", "warn"), (job["engine"], "ok")],
        )
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("åˆ·æ–°è®¡ç®—çŠ¶æ€", use_container_width=True):
                st.rerun()
        with c2:
            if st.button("å–æ¶ˆè®¡ç®—", type="secondary", use_container_width=True):
                cancel_background_job()
                st.warning("å·²è¯·æ±‚å–æ¶ˆå½“å‰è®¡ç®—ã€‚")
                st.rerun()
        log_text = load_file_text(Path(job["log_path"]))
        if log_text:
            with st.expander("æŸ¥çœ‹å®æ—¶æ§åˆ¶å°æ—¥å¿—", expanded=False):
                st.code(log_text[-5000:], language="text")
    elif st.session_state.get("last_finished_out_dir"):
        out_dir = Path(st.session_state.last_finished_out_dir)
        if (out_dir / "report.json").exists():
            st.success(f"ä¸Šä¸€æ¬¡è®¡ç®—å·²å®Œæˆï¼š{out_dir}")
        elif (out_dir / "cancelled.txt").exists():
            st.warning(f"ä¸Šä¸€æ¬¡è®¡ç®—å·²å–æ¶ˆï¼š{out_dir}")
        elif (out_dir / "console.log").exists():
            st.warning(f"ä¸Šä¸€æ¬¡è®¡ç®—ç»“æŸï¼Œä½†æœªç”Ÿæˆ report.jsonï¼š{out_dir}")


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
      ß^¶¶‰ËkºwµçAĞ¹•Ğ ‰•ÉÉ½Èˆ¤½È€ˆˆ°(€€€€€€€€€€€€€€€ô(€€€€€€€€€€€€¤(€€€€€€€‘…Ñ…™É…µ•}™É½´¡É½İÌ¤(€€€İ¥Ñ Ñ…ˆÈè(€€€€€€€‘…Ñ…™É…µ•}™É½´¡‘…Ñ„¹•Ğ ‰Ù…±¥‘…Ñ¥½¸ˆ°mt¤¤(€€€İ¥Ñ Ñ…ˆÌè(€€€€€€€‘…Ñ…™É…µ•}™É½´¡‘…Ñ„¹•Ğ ‰É•Á…¥ÉÌˆ°mt¤¤(€€€İ¥Ñ Ñ…ˆĞè(€€€€€€€É•¹‘•É}±±µ}Ù¥•Ü¡‘…Ñ„¤(€€€İ¥Ñ Ñ…ˆÔè(€€€€€€€É•¹‘•É}É•Á½ÉÑ}ÁÉ•Ù¥•Ü¡‘…Ñ„¤(()‘•˜É•¹‘•É}¡¥ÍÑ½Éå}µ…¹…•È ¤€´ø9½¹”è(€€€Ñ¥Ñ±•}½°°É•™É•Í¡}½°€ôÍĞ¹½±Õµ¹Ì¡lÔ°€Åt¤(€€€İ¥Ñ Ñ¥Ñ±•}½°è(€€€€€€€ÍĞ¹µ…É­‘½İ¸ ˆŒŒŒƒ–:–>Ë¢º‡º_¢ºÃ–öTˆ¤(€€€İ¥Ñ É•™É•Í¡}½°è(€€€€€€€¥˜ÍĞ¹‰ÕÑÑ½¸ ‹–"ßšZÃ–:–>Ë¢ºÃ–öTˆ°ÕÍ•}½¹Ñ…¥¹•É}İ¥‘Ñ õQÉÕ”¤è(€€€€€€€€€€€ÍĞ¹É•ÉÕ¸ ¤(€€€É•½É‘Ì€ô±½…‘}¡¥ÍÑ½Éå}É•½É‘Ì ¤(€€€¥˜¹½ĞÉ•½É‘Ìè(€€€€€€€ÍĞ¹¥¹™¼ ‹šjš^ƒ–:–>Ë¢ºÃ–öW¢şC¢†3’âš²‡¢º‡º_–B;¾ò3¢şg¦3’òk¢«–*£–ë:Ã¢ºÃ–öWˆ¤(€€€€€€€É•ÑÕÉ¸((€€€ÍĞ¹Í•ÍÍ¥½¹}ÍÑ…Ñ”¹Í•Ñ‘•™…Õ±Ğ ‰¡¥ÍÑ½Éå}•‘¥Ñ½É}Ù•ÉÍ¥½¸ˆ°€À¤((€€€Ñ…‰±•}É½İÌ€ôl(€€€€€€€ì(€€€€€€€€€€€€‹¢ºÃ–öU%ˆè¥Ñ•µl‹n»–öW–B4‰t°(€€€€€€€€€€€€‹¦'š.¤ˆè…±Í”°(€€€€€€€€€€€€‹º_’ú,ˆè¥Ñ•µl‹º_’ú,‰t°(€€€€€€€€€€€€‹–Ş—¢/–>¿¢†0ˆè¥Ñ•µl‹–Ş—¢/–>¿¢†0‰t°(€€€€€€€€€€€€‹šRÛšVlˆè¥Ñ•µl‹šRÛšVl‰t°(€€€€€€€€€€€€‹–Âw¢¾Wš²‡šVÀˆè¥Ñ•µl‹–Âw¢¾Wš²‡šVÀ‰t°(€€€€€€€€€€€€‹¢şC¢†3š^Û¦^Ğˆè¥Ñ•µl‹¢şC¢†3š^Û¦^Ğ‰t°(€€€€€€€ô(€€€€€€€™½È¥Ñ•´¥¸É•½É‘Ì(€€€t(€€€•‘¥Ñ½É}­•ä€ô˜‰¡¥ÍÑ½Éå}É•½É‘}Í•±•Ñ½É}íÍĞ¹Í•ÍÍ¥½¹}ÍÑ…Ñ”¹¡¥ÍÑ½Éå}•‘¥Ñ½É}Ù•ÉÍ¥½¹ôˆ(€€€•‘¥Ñ•‘}É½İÌ€ôÍĞ¹‘…Ñ…}•‘¥Ñ½È (€€€€€€€Á¹…Ñ…É…µ”¡Ñ…‰±•}É½İÌ¤°(€€€€€€€ÕÍ•}½¹Ñ…¥¹•É}İ¥‘Ñ õQÉÕ”°(€€€€€€€‘¥Í…‰±•õl‹º_’ú,ˆ°€‹–Ş—¢/–>¿¢†0ˆ°€‹šRÛšVlˆ°€‹–Âw¢¾Wš²‡šVÀˆ°€‹¢şC¢†3š^Û¦^Ğ‰t°(€€€€€€€½±Õµ¹}½¹™¥œõì(€€€€€€€€€€€€‹¢ºÃ–öU%ˆè9½¹”°(€€€€€€€€€€€€‹¦'š.¤ˆèÍĞ¹½±Õµ¹}½¹™¥œ¹¡•­‰½á½±Õµ¸ (€€€€€€€€€€€€€€€€‹¦'š.¤ˆ°(€€€€€€€€€€€€€€€¡•±Àô‹–.û¦'’âšv‡š"[–’kšv‡–:–>Ë¢ºÃ–öW–B;¾ò3–>¿’î—š&ç¦?–"ƒ¦f“ˆ°(€€€€€€€€€€€€€€€İ¥‘Ñ ô‰Íµ…±°ˆ°(€€€€€€€€€€€€€€€…±¥¹µ•¹Ğô‰•¹Ñ•Èˆ°(€€€€€€€€€€€€€€€‘•™…Õ±Ğõ…±Í”°(€€€€€€€€€€€€¤°(€€€€€€€€€€€€‹¢şC¢†3š^Û¦^ĞˆèÍĞ¹½±Õµ¹}½¹™¥œ¹Q•áÑ½±Õµ¸ (€€€€€€€€€€€€€€€€‹¢şC¢†3š^Û¦^Ğˆ°(€€€€€€€€€€€€€€€İ¥‘Ñ ô‰µ•‘¥Õ´ˆ°(€€€€€€€€€€€€€€€…±¥¹µ•¹Ğô‰•¹Ñ•Èˆ°(€€€€€€€€€€€€¤°(€€€€€€€ô°(€€€€€€€­•äõ•‘¥Ñ½É}­•ä°(€€€€¤(€€€Í•±•Ñ•‘}‘¥ÉÌ€ôÍ•Ğ (€€€€€€€•‘¥Ñ•‘}É½İÌ¹±½m•‘¥Ñ•‘}É½İÍl‹¦'š.¤‰t¹…ÍÑåÁ”¡‰½½°¤°€‹¢ºÃ–öU%‰t¹…ÍÑåÁ”¡ÍÑÈ¤¹Ñ½±¥ÍĞ ¤(€€€€€€€¥˜€‹¢ºÃ–öU%ˆ¥¸•‘¥Ñ•‘}É½İÌ¹½±Õµ¹Ì(€€€€€€€•±Í”mt(€€€€¤(€€€Í•±•Ñ•‘}É•½É‘Ì€ôm¥Ñ•´™½È¥Ñ•´¥¸É•½É‘Ì¥˜¥Ñ•µl‹n»–öW–B4‰t¥¸Í•±•Ñ•‘}‘¥ÉÍt((€€€Í•±•Ñ•‘}±…‰•°€ôÍĞ¹Í•±•Ñ‰½à ‹¦'š.§¢šš~—r/j–:–>Ë¢ºÃ–öTˆ°m¥Ñ•µl‹šbû’ë–B7À‰t™½È¥Ñ•´¥¸É•½É‘Ít¤(€€€Í•±•Ñ•€ô¹•áĞ¡¥Ñ•´™½È¥Ñ•´¥¸É•½É‘Ì¥˜¥Ñ•µl‹šbû’ë–B7À‰t€ôôÍ•±•Ñ•‘}±…‰•°¤(€€€ŒÄ°ŒÈ€ôÍĞ¹½±Õµ¹Ì¡lÄ°€Åt¤(€€€İ¥Ñ ŒÄè(€€€€€€€½Á•¹}±¥­•€ôÍĞ¹‰ÕÑÑ½¸ ‹š&O–ò¢¾—–:–>Ë¢ºÃ–öTˆ°ÕÍ•}½¹Ñ…¥¹•É}İ¥‘Ñ õQÉÕ”¤(€€€İ¥Ñ ŒÈè(€€€€€€€‘•±•Ñ•}±¥­•€ôÍĞ¹‰ÕÑÑ½¸ (€€€€€€€€€€€˜‹–"ƒ¦f“¦'’â·–:–>Ë¢ºÃ–öW¾ò!í±•¸¡Í•±•Ñ•‘}É•½É‘Ì¥÷¾ò$ˆ°(€€€€€€€€€€€‘¥Í…‰±•õ¹½ĞÍ•±•Ñ•‘}É•½É‘Ì°(€€€€€€€€€€€ÕÍ•}½¹Ñ…¥¹•É}İ¥‘Ñ õQÉÕ”°(€€€€€€€€¤((€€€¥˜‘•±•Ñ•}±¥­•è(€€€€€€€™…¥±•è±¥ÍÑmÍÑÉt€ômt(€€€€€€€™½ÈÉ•½É¥¸Í•±•Ñ•‘}É•½É‘Ìè(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€‘•±•Ñ•}¡¥ÍÑ½Éå}É•½É¡É•½É¤(€€€€€€€€€€€•á•ÁĞá•ÁÑ¥½¸…Ì•áŒè(€€€€€€€€€€€€€€€™…¥±•¹…ÁÁ•¹¡˜‰íÉ•½É‘lŸn»–öW–B4u÷¾òiíÑåÁ”¡•áŒ¤¹}}¹…µ•}}ôèí•áôˆ¤(€€€€€€€¥˜™…¥±•è(€€€€€€€€€€€ÍĞ¹•ÉÉ½È ‹¦£–"–:–>Ë¢ºÃ–öW–"ƒ¦f“–’Ç¢Ò—¾òiq¸ˆ€¬€‰q¸ˆ¹©½¥¸¡™…¥±•¤¤(€€€€€€€•±Í”è(€€€€€€€€€€€ÍĞ¹Í•ÍÍ¥½¹}ÍÑ…Ñ”¹¡¥ÍÑ½Éå}•‘¥Ñ½É}Ù•ÉÍ¥½¸€¬ô€Ä(€€€€€€€€€€€ÍĞ¹ÍÕ•ÍÌ¡˜‹–ŞË–"ƒ¦fí±•¸¡Í•±•Ñ•‘}É•½É‘Ì¥ôƒšv‡–:–>Ë¢ºÃ–öWˆ¤(€€€€€€€€€€€ÍĞ¹É•ÉÕ¸ ¤((€€€¥˜½Á•¹}±¥­•è(€€€€€€€‘…Ñ„€ô±½…‘}©Í½¸¡A…Ñ ¡Í•±•Ñ•‘l‹š*—–F))M=8‰t¤¤(€€€€€€€¥˜‘…Ñ„è(€€€€€€€€€€€ÍĞ¹µ…É­‘½İ¸¡˜ˆŒŒŒŒƒš¶–r£š~—r/¾òiíÍ•±•Ñ•‘lŸn»–öW–B4uôˆ¤(€€€€€€€€€€€É•¹‘•É}É•Á½ÉÑ}‘…Ñ„¡‘…Ñ„¤(€€€€€€€•±Í”è(€€€€€€€€€€€ÍĞ¹•ÉÉ½È ‹š^ƒšÎW¢¾ï–>[¢¾—–:–>Ë¢ºÃ–öWjÉ•Á½ÉĞ¹©Í½»ˆ¤(()‘•˜}É•¹‘•É}É••¹Ñ}É•ÍÕ±Ñ}¥™}…Ù…¥±…‰±” ¤€´ø9½¹”è(€€€™¥¹¥Í¡•‘}‘¥È€ôA…Ñ ¡ÍĞ¹Í•ÍÍ¥½¹}ÍÑ…Ñ”¹±…ÍÑ}™¥¹¥Í¡•‘}½ÕÑ}‘¥È¤¥˜ÍĞ¹Í•ÍÍ¥½¹}ÍÑ…Ñ”¹•Ğ ‰±…ÍÑ}™¥¹¥Í¡•‘}½ÕÑ}‘¥Èˆ¤•±Í”9½¹”(€€€¥˜™¥¹¥Í¡•‘}‘¥È…¹€¡™¥¹¥Í¡•‘}‘¥È€¼€‰É•Á½ÉĞ¹©Í½¸ˆ¤¹•á¥ÍÑÌ ¤è(€€€€€€€‘…Ñ„€ô±½…‘}©Í½¸¡™¥¹¥Í¡•‘}‘¥È€¼€‰É•Á½ÉĞ¹©Í½¸ˆ¤(€€€€€€€¥˜‘…Ñ„è(€€€€€€€€€€€ÍĞ¹µ…É­‘½İ¸ ˆŒŒŒƒšr¢şG’âš²‡¢º‡º_îOšzpˆ¤(€€€€€€€€€€€É•¹‘•É}É•Á½ÉÑ}‘…Ñ„¡‘…Ñ„¤(()‘•˜}É•¹‘•É}±¥Ù•}…É•…}‰½‘ä ¤€´ø9½¹”è(€€€É•¹‘•É}©½‰}½¹ÑÉ½° ¤(€€€}É•¹‘•É}É••¹Ñ}É•ÍÕ±Ñ}¥™}…Ù…¥±…‰±” ¤(()¥˜¡…Í…ÑÑÈ¡ÍĞ°€‰™É…µ•¹Ğˆ¤è(€€€É•¹‘•É}±¥Ù•}…É•„€ôÍĞ¹™É…µ•¹Ğ¡ÉÕ¹}•Ù•ÉäôÈ¤¡}É•¹‘•É}±¥Ù•}…É•…}‰½‘ä¤)•±Í”è(€€€É•¹‘•É}±¥Ù•}…É•„€ô}É•¹‘•É}±¥Ù•}…É•…}‰½‘ä(()‘•˜}±…Ñ•ÍÑ}É•Á½ÉÑ}½¹Ñ•áĞ ¤€´ø‘¥ÑmÍÑÈ°¹åtğ9½¹”è(€€€½ÕÑ}‘¥É}Ñ•áĞ€ôÍĞ¹Í•ÍÍ¥½¹}ÍÑ…Ñ”¹•Ğ ‰±…ÍÑ}™¥¹¥Í¡•‘}½ÕÑ}‘¥Èˆ¤(€€€¥˜¹½Ğ½ÕÑ}‘¥É}Ñ•áĞè(€€€€€€€É•ÑÕÉ¸9½¹”(€€€É•Á½ÉÑ}Á…Ñ €ôA…Ñ ¡½ÕÑ}‘¥É}Ñ•áĞ¤€¼€‰É•Á½ÉĞ¹©Í½¸ˆ(€€€‘…Ñ„€ô±½…‘}©Í½¸¡É•Á½ÉÑ}Á…Ñ ¤(€€€¥˜¹½Ğ‘…Ñ„è(€€€€€€€É•ÑÕÉ¸9½¹”(€€€…ÑÑ•µÁÑÌ€ô‘…Ñ„¹•Ğ ‰…ÑÑ•µÁÑÌˆ°mt¤(€€€±…ÍÑ}…ÑÑ•µÁĞ€ô…ÑÑ•µÁÑÍl´Åt¥˜…ÑÑ•µÁÑÌ•±Í”íô(€€€É•ÑÕÉ¸ì(€€€€€€€€‰…Í•}Á…Ñ ˆè‘…Ñ„¹•Ğ ‰…Í•}Á…Ñ ˆ¤°(€€€€€€€€‰•¹¥¹••É¥¹}™•…Í¥‰±”ˆè‘…Ñ„¹•Ğ ‰ÍÕ•ÍÌˆ¤°(€€€€€€€€‰Í½±Ù•É}½¹Ù•É•ˆè‘…Ñ„¹•Ğ ‰Í½±Ù•É}½¹Ù•É•ˆ°±…ÍÑ}…ÑÑ•µÁĞ¹•Ğ ‰ÍÕ•ÍÌˆ¤¤°(€€€€€€€€‰…ÑÑ•µÁÑ}½Õ¹Ğˆè±•¸¡…ÑÑ•µÁÑÌ¤°(€€€€€€€€‰±…ÍÑ}…ÑÑ•µÁĞˆèì(€€€€€€€€€€€€‰¹…µ”ˆè±…ÍÑ}…ÑÑ•µÁĞ¹•Ğ ‰¹…µ”ˆ¤°(€€€€€€€€€€€€‰ÍÕ•ÍÌˆè±…ÍÑ}…ÑÑ•µÁĞ¹•Ğ ‰ÍÕ•ÍÌˆ¤°(€€€€€€€€€€€€‰™•…Í¥‰±”ˆè±…ÍÑ}…ÑÑ•µÁĞ¹•Ğ ‰™•…Í¥‰±”ˆ¤°(€€€€€€€€€€€€‰•ÉÉ½Èˆè±…ÍÑ}…ÑÑ•µÁĞ¹•Ğ ‰•ÉÉ½Èˆ¤°(€€€€€€€€€€€€‰Ù¥½±…Ñ¥½¹Ìˆè±…ÍÑ}…ÑÑ•µÁĞ¹•Ğ ‰Ù¥½±…Ñ¥½¹Ìˆ°mt¥lèÈÁt°(€€€€€€€€€€€€‰Å}±¥µ¥Ñ}•Ù•¹ÑÌˆè±…ÍÑ}…ÑÑ•µÁĞ¹•Ğ ‰Å}±¥µ¥Ñ}•Ù•¹ÑÌˆ°mt¥lèÈÁt°(€€€€€€€ô°(€€€€€€€€‰É•Á…¥ÉÌˆè‘…Ñ„¹•Ğ ‰É•Á…¥ÉÌˆ°mt¥lèÈÁt°(€€€ô(()‘•˜}¹•İ}¡…Ñ}½¹Ù•ÉÍ…Ñ¥½¸ ¤€´ø‘¥ÑmÍÑÈ°¹åtè(€€€¹½Ü€ô‘…Ñ•Ñ¥µ”¹¹½Ü ¤¹¥Í½™½Éµ…Ğ¡Ñ¥µ•ÍÁ•Œô‰Í•½¹‘Ìˆ¤(€€€É•ÑÕÉ¸ì(€€€€€€€€‰¥ˆèÕÕ¥Ğ ¤¹¡•à°(€€€€€€€€‰Ñ¥Ñ±”ˆè€‹šZÃ–¾ç¢¾tˆ°(€€€€€€€€‰É•…Ñ•‘}…Ğˆè¹½Ü°(€€€€€€€€‰ÕÁ‘…Ñ•‘}…Ğˆè¹½Ü°(€€€€€€€€‰µ•ÍÍ…•Ìˆèmt°(€€€ô(()‘•˜±½…‘}¡…Ñ}¡¥ÍÑ½Éä ¤€´ø‘¥ÑmÍÑÈ°¹åtè(€€€‘…Ñ„€ô±½…‘}©Í½¸¡!Q}!%MQ=Ie}AQ ¤(€€€¥˜¹½Ğ¥Í¥¹ÍÑ…¹”¡‘…Ñ„°‘¥Ğ¤½È¹½Ğ¥Í¥¹ÍÑ…¹”¡‘…Ñ„¹•Ğ ‰½¹Ù•ÉÍ…Ñ¥½¹Ìˆ¤°±¥ÍĞ¤è(€€€€€€€É•ÑÕÉ¸ì‰Ù•ÉÍ¥½¸ˆè€Ä°€‰½¹Ù•ÉÍ…Ñ¥½¹Ìˆèmuô((€€€½¹Ù•ÉÍ…Ñ¥½¹Ì€ômt(€€€™½È¥Ñ•´¥¸‘…Ñ…l‰½¹Ù•ÉÍ…Ñ¥½¹Ì‰tè(€€€€€€€¥˜¹½Ğ¥Í¥¹ÍÑ…¹”¡¥Ñ•´°‘¥Ğ¤½È¹½Ğ¥Ñ•´¹•Ğ ‰¥ˆ¤½È¹½Ğ¥Í¥¹ÍÑ…¹”¡¥Ñ•´¹•Ğ ‰µ•ÍÍ…•Ìˆ¤°±¥ÍĞ¤è(€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€½¹Ù•ÉÍ…Ñ¥½¹Ì¹…ÁÁ•¹¡¥Ñ•´¤(€€€É•ÑÕÉ¸ì‰Ù•ÉÍ¥½¸ˆè€Ä°€‰½¹Ù•ÉÍ…Ñ¥½¹Ìˆè½¹Ù•ÉÍ…Ñ¥½¹Íô(()‘•˜Í…Ù•}¡…Ñ}¡¥ÍÑ½Éä¡¡¥ÍÑ½Éäè‘¥ÑmÍÑÈ°¹åt¤€´ø9½¹”è(€€€IU9M}%H¹µ­‘¥È¡Á…É•¹ÑÌõQÉÕ”°•á¥ÍÑ}½¬õQÉÕ”¤(€€€Ñ•µÁ}Á…Ñ €ô!Q}!%MQ=Ie}AQ ¹İ¥Ñ¡}ÍÕ™™¥à ˆ¹ÑµÀˆ¤(€€€Ñ•µÁ}Á…Ñ ¹İÉ¥Ñ•}Ñ•áĞ (€€€€€€€©Í½¸¹‘ÕµÁÌ¡¡¥ÍÑ½Éä°•¹ÍÕÉ•}…Í¥¤õ…±Í”°¥¹‘•¹ĞôÈ°‘•™…Õ±ĞõÍÑÈ¤°(€€€€€€€•¹½‘¥¹œô‰ÕÑ˜´àˆ°(€€€€¤(€€€Ñ•µÁ}Á…Ñ ¹É•Á±…”¡!Q}!%MQ=Ie}AQ ¤(()‘•˜}¡…Ñ}Ñ¥Ñ±”¡ÁÉ½µÁĞèÍÑÈ¤€´øÍÑÈè(€€€Ñ¥Ñ±”€ô€ˆ€ˆ¹©½¥¸¡ÁÉ½µÁĞ¹ÍÁ±¥Ğ ¤¤(€€€É•ÑÕÉ¸Ñ¥Ñ±”¥˜±•¸¡Ñ¥Ñ±”¤€ğô€ÈĞ•±Í”Ñ¥Ñ±•lèÈÑt€¬€‹Š˜ˆ(()‘•˜}¡…Ñ}½ÁÑ¥½¹}±…‰•°¡½¹Ù•ÉÍ…Ñ¥½¸è‘¥ÑmÍÑÈ°¹åt¤€´øÍÑÈè(€€€ÕÁ‘…Ñ•‘}…Ğ€ôÍÑÈ¡½¹Ù•ÉÍ…Ñ¥½¸¹•Ğ ‰ÕÁ‘…Ñ•‘}…Ğˆ°€ˆˆ¤¤¹É•Á±…” ‰Pˆ°€ˆ€ˆ¤(€€€É•ÑÕÉ¸˜‰í½¹Ù•ÉÍ…Ñ¥½¸¹•Ğ Ñ¥Ñ±”œ¤½È€ŸšZÃ–¾ç¢¾t÷íÕÁ‘…Ñ•‘}…ÑlèÄÙuôˆ(()‘•˜É•¹‘•É}¡…Ğ¡½¹ÑÉ½±Ìè‘¥ÑmÍÑÈ°¹åt¤€´ø9½¹”è(€€€ÍĞ¹ÍÕ‰¡•…‘•È ‹šö»šÖšfë¢÷¦^»¶Pˆ¤(€€€ÍĞ¹…ÁÑ¥½¸ ‹–>¿¢¾‹¦^»šö»šÖ¢º‡º_–:Bº_’ú/šVÃš6»šRÛšVo¦^»¦Šc¾ò3’î—–>+šr¢şG’âš²‡¢º‡º_îOšzs–:–>Ë–¾ç¢¾w’òk¢«–*£’şw–¶c–r£šr³šrëˆ¤(€€€¡¥ÍÑ½Éä€ô±½…‘}¡…Ñ}¡¥ÍÑ½Éä ¤(€€€¥˜¹½Ğ¡¥ÍÑ½Éål‰½¹Ù•ÉÍ…Ñ¥½¹Ì‰tè(€€€€€€€¡¥ÍÑ½Éål‰½¹Ù•ÉÍ…Ñ¥½¹Ì‰t¹…ÁÁ•¹¡}¹•İ}¡…Ñ}½¹Ù•ÉÍ…Ñ¥½¸ ¤¤(€€€€€€€Í…Ù•}¡…Ñ}¡¥ÍÑ½Éä¡¡¥ÍÑ½Éä¤((€€€½¹Ù•ÉÍ…Ñ¥½¹Í}‰å}¥€ôí¥Ñ•µl‰¥‰tè¥Ñ•´™½È¥Ñ•´¥¸¡¥ÍÑ½Éål‰½¹Ù•ÉÍ…Ñ¥½¹Ì‰uô(€€€É•ÅÕ•ÍÑ•‘}¥€ôÍĞ¹Í•ÍÍ¥½¹}ÍÑ…Ñ”¹•Ğ ‰¡…Ñ}½¹Ù•ÉÍ…Ñ¥½¹}Í•±•Ñ½Èˆ¤(€€€ÕÉÉ•¹Ñ}¥€ôÉ•ÅÕ•ÍÑ•‘}¥¥˜É•ÅÕ•ÍÑ•‘}¥¥¸½¹Ù•ÉÍ…Ñ¥½¹Í}‰å}¥•±Í”ÍĞ¹Í•ÍÍ¥½¹}ÍÑ…Ñ”¹•Ğ ‰ÕÉÉ•¹Ñ}¡…Ñ}¥ˆ¤(€€€¥˜ÕÉÉ•¹Ñ}¥¹½Ğ¥¸½¹Ù•ÉÍ…Ñ¥½¹Í}‰å}¥è(€€€€€€€ÕÉÉ•¹Ñ}¥€ôµ…à¡¡¥ÍÑ½Éål‰½¹Ù•ÉÍ…Ñ¥½¹Ì‰t°­•äõ±…µ‰‘„¥Ñ•´è¥Ñ•´¹•Ğ ‰ÕÁ‘…Ñ•‘}…Ğˆ°€ˆˆ¤¥l‰¥‰t(€€€ÍĞ¹Í•ÍÍ¥½¹}ÍÑ…Ñ”¹ÕÉÉ•¹Ñ}¡…Ñ}¥€ôÕÉÉ•¹Ñ}¥(€€€½¹Ù•ÉÍ…Ñ¥½¸€ô½¹Ù•ÉÍ…Ñ¥½¹Í}‰å}¥‘mÕÉÉ•¹Ñ}¥‘t(€€€µ•ÍÍ…•Ì€ô½¹Ù•ÉÍ…Ñ¥½¹l‰µ•ÍÍ…•Ì‰t((€€€½¹™¥œ€ô115½¹™¥œ¹™É½µ}•¹Ø (€€€€€€€ÁÉ½Ù¥‘•Èõ½¹ÑÉ½±Íl‰±±µ}ÁÉ½Ù¥‘•È‰t°(€€€€€€€µ½‘•°õ½¹ÑÉ½±Íl‰±±µ}µ½‘•°‰t½È9½¹”°(€€€€€€€‰…Í•}ÕÉ°õ½¹ÑÉ½±Íl‰±±µ}‰…Í•}ÕÉ°‰t½È9½¹”°(€€€€€€€…Á¥}­•äõ½¹ÑÉ½±Íl‰±±µ}…Á¥}­•ä‰t½È9½¹”°(€€€€¤((€€€¥˜½¹ÑÉ½±Íl‰±±µ}ÁÉ½Ù¥‘•È‰t€ôô€‰½™˜ˆè(€€€€€€€ÍĞ¹¥¹™¼ ‹¢¾ß–r£–Ş›’úŸŠs–’Ÿš¢‡–z/Šw’â·¦'š.¤••ÁM••¬ƒš"X-¥µ§ˆ¤(€€€•±¥˜¹½Ğ½¹™¥œ¹•¹…‰±•è(€€€€€€€•¹Ù}¹…µ”€ô€‰AM-}A%}-dˆ¥˜½¹ÑÉ½±Íl‰±±µ}ÁÉ½Ù¥‘•È‰t€ôô€‰‘••ÁÍ••¬ˆ•±Í”€‰-%5%}A%}-dˆ(€€€€€€€ÍĞ¹İ…É¹¥¹œ¡˜‹šr«ššÖ/–"Ãš¢‡–z/–¾¦J—¾ò3¢¾ß–#¢ºûö»Îïî:¿–Š–>c¦<í•¹Ù}¹…µ•÷ˆ¤(€€€•±Í”è(€€€€€€€ÍĞ¹…ÁÑ¥½¸¡˜‹–öO–&7š¢‡–z/¾òií½¹™¥œ¹µ½‘•±ôƒ
Üí½¹ÑÉ½±Íl±±µ}ÁÉ½Ù¥‘•Èuôˆ¤((€€€µ•ÍÍ…•Í}İ¥¹‘½Ü€ôÍĞ¹½¹Ñ…¥¹•È¡¡•¥¡ĞôÔÀÀ°‰½É‘•ÈõQÉÕ”¤(€€€İ¥Ñ µ•ÍÍ…•Í}İ¥¹‘½Üè(€€€€€€€¥˜¹½Ğµ•ÍÍ…•Ìè(€€€€€€€€€€€İ¥Ñ ÍĞ¹¡…Ñ}µ•ÍÍ…” ‰…ÍÍ¥ÍÑ…¹Ğˆ¤è(€€€€€€€€€€€€€€€ÍĞ¹µ…É­‘½İ¸ ‹’öƒ––÷¾ò3š"Gšb¿šö»šÖ¢º‡º_šfë¢÷’öO’öƒ–>¿’î—nÓš:—š>?¢şÃ¦^»¦Šc¾ò3’ú/–š¾òh¨«’âë’î’æ AXƒ¢*
ç’òk¢ö³š"@ADƒ¢*
ç¾ò|¨¨ˆ¤(€€€€€€€•±Í”è(€€€€€€€€€€€™½Èµ•ÍÍ…”¥¸µ•ÍÍ…•Ìè(€€€€€€€€€€€€€€€İ¥Ñ ÍĞ¹¡…Ñ}µ•ÍÍ…”¡µ•ÍÍ…•l‰É½±”‰t¤è(€€€€€€€€€€€€€€€€€€€ÍĞ¹µ…É­‘½İ¸¡µ•ÍÍ…•l‰½¹Ñ•¹Ğ‰t¤((€€€ÁÉ½µÁĞ€ôÍĞ¹¡…Ñ}¥¹ÁÕĞ ‹¢úO–—’öƒj¦^»¦Šc¾ò3’ú/–š¾òk–"šzCšr¢şG’âš²‡šö»šÖ¢º‡º_’âë’î’æ#šÊ‡šr'šRÛšVlˆ¤((€€€¡¥ÍÑ½Éå}½°°¹•İ}½°°‘•±•Ñ•}½°€ôÍĞ¹½±Õµ¹Ì¡lĞ°€Ä°€Åt¤(€€€İ¥Ñ ¹•İ}½°è(€€€€€€€¥˜ÍĞ¹‰ÕÑÑ½¸ ‹šZÃ–îë–¾ç¢¾tˆ°İ¥‘Ñ ô‰ÍÑÉ•Ñ ˆ¤è(€€€€€€€€€€€¹•İ}½¹Ù•ÉÍ…Ñ¥½¸€ô}¹•İ}¡…Ñ}½¹Ù•ÉÍ…Ñ¥½¸ ¤(€€€€€€€€€€€¡¥ÍÑ½Éål‰½¹Ù•ÉÍ…Ñ¥½¹Ì‰t¹…ÁÁ•¹¡¹•İ}½¹Ù•ÉÍ…Ñ¥½¸¤(€€€€€€€€€€€Í…Ù•}¡…Ñ}¡¥ÍÑ½Éä¡¡¥ÍÑ½Éä¤(€€€€€€€€€€€ÍĞ¹Í•ÍÍ¥½¹}ÍÑ…Ñ”¹ÕÉÉ•¹Ñ}¡…Ñ}¥€ô¹•İ}½¹Ù•ÉÍ…Ñ¥½¹l‰¥‰t(€€€€€€€€€€€ÍĞ¹Í•ÍÍ¥½¹}ÍÑ…Ñ”¹¡…Ñ}½¹Ù•ÉÍ…Ñ¥½¹}Í•±•Ñ½È€ô¹•İ}½¹Ù•ÉÍ…Ñ¥½¹l‰¥‰t(€€€€€€€€€€€ÍĞ¹É•ÉÕ¸ ¤(€€€İ¥Ñ ‘•±•Ñ•}½°è(€€€€€€€İ¥Ñ ÍĞ¹Á½Á½Ù•È ‹–"ƒ¦f“–¾ç¢¾tˆ°İ¥‘Ñ ô‰ÍÑÉ•Ñ ˆ¤è(€€€€€€€€€€€ÍĞ¹İ…É¹¥¹œ ‹–"ƒ¦f“–B;š^ƒšÎWš‹–’7¾ò3†»–ºk–"ƒ¦f“–öO–&7–¾ç¢¾w–B_¾ò|ˆ¤(€€€€€€€€€€€¥˜ÍĞ¹‰ÕÑÑ½¸ ‹†»¢º“–"ƒ¦fˆ°ÑåÁ”ô‰ÁÉ¥µ…Éäˆ°İ¥‘Ñ ô‰ÍÑÉ•Ñ ˆ¤è(€€€€€€€€€€€€€€€¡¥ÍÑ½Éål‰½¹Ù•ÉÍ…Ñ¥½¹Ì‰t€ôl(€€€€€€€€€€€€€€€€€€€¥Ñ•´™½È¥Ñ•´¥¸¡¥ÍÑ½Éål‰½¹Ù•ÉÍ…Ñ¥½¹Ì‰t¥˜¥Ñ•µl‰¥‰t€„ôÕÉÉ•¹Ñ}¥(€€€€€€€€€€€€€€€t(€€€€€€€€€€€€€€€¥˜¹½Ğ¡¥ÍÑ½Éål‰½¹Ù•ÉÍ…Ñ¥½¹Ì‰tè(€€€€€€€€€€€€€€€€€€€¡¥ÍÑ½Éål‰½¹Ù•ÉÍ…Ñ¥½¹Ì‰t¹…ÁÁ•¹¡}¹•İ}¡…Ñ}½¹Ù•ÉÍ…Ñ¥½¸ ¤¤(€€€€€€€€€€€€€€€¹•áÑ}½¹Ù•ÉÍ…Ñ¥½¸€ôµ…à (€€€€€€€€€€€€€€€€€€€¡¥ÍÑ½Éål‰½¹Ù•ÉÍ…Ñ¥½¹Ì‰t°(€€€€€€€€€€€€€€€€€€€­•äõ±…µ‰‘„¥Ñ•´è¥Ñ•´¹•Ğ ‰ÕÁ‘…Ñ•‘}…Ğˆ°€ˆˆ¤°(€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€€€€Í…Ù•}¡…Ñ}¡¥ÍÑ½Éä¡¡¥ÍÑ½Éä¤(€€€€€€€€€€€€€€€ÍĞ¹Í•ÍÍ¥½¹}ÍÑ…Ñ”¹ÕÉÉ•¹Ñ}¡…Ñ}¥€ô¹•áÑ}½¹Ù•ÉÍ…Ñ¥½¹l‰¥‰t(€€€€€€€€€€€€€€€ÍĞ¹Í•ÍÍ¥½¹}ÍÑ…Ñ”¹¡…Ñ}½¹Ù•ÉÍ…Ñ¥½¹}Í•±•Ñ½È€ô¹•áÑ}½¹Ù•ÉÍ…Ñ¥½¹l‰¥‰t(€€€€€€€€€€€€€€€ÍĞ¹É•ÉÕ¸ ¤(€€€İ¥Ñ ¡¥ÍÑ½Éå}½°è(€€€€€€€Í½ÉÑ•‘}½¹Ù•ÉÍ…Ñ¥½¹Ì€ôÍ½ÉÑ• (€€€€€€€€€€€¡¥ÍÑ½Éål‰½¹Ù•ÉÍ…Ñ¥½¹Ì‰t°(€€€€€€€€€€€­•äõ±…µ‰‘„¥Ñ•´è¥Ñ•´¹•Ğ ‰ÕÁ‘…Ñ•‘}…Ğˆ°€ˆˆ¤°(€€€€€€€€€€€É•Ù•ÉÍ”õQÉÕ”°(€€€€€€€€¤(€€€€€€€½ÁÑ¥½¹}¥‘Ì€ôm¥Ñ•µl‰¥‰t™½È¥Ñ•´¥¸Í½ÉÑ•‘}½¹Ù•ÉÍ…Ñ¥½¹Ít(€€€€€€€½ÁÑ¥½¹}±½½­ÕÀ€ôí¥Ñ•µl‰¥‰tè¥Ñ•´™½È¥Ñ•´¥¸Í½ÉÑ•‘}½¹Ù•ÉÍ…Ñ¥½¹Íô(€€€€€€€Í•±•Ñ•‘}¥¹‘•à€ô½ÁÑ¥½¹}¥‘Ì¹¥¹‘•à¡ÕÉÉ•¹Ñ}¥¤¥˜ÕÉÉ•¹Ñ}¥¥¸½ÁÑ¥½¹}¥‘Ì•±Í”€À(€€€€€€€ÍĞ¹Í•±•Ñ‰½à (€€€€€€€€€€€€‹–:–>Ë–¾ç¢¾tˆ°(€€€€€€€€€€€½ÁÑ¥½¹}¥‘Ì°(€€€€€€€€€€€¥¹‘•àõÍ•±•Ñ•‘}¥¹‘•à°(€€€€€€€€€€€™½Éµ…Ñ}™Õ¹Œõ±…µ‰‘„¥Ñ•µ}¥è}¡…Ñ}½ÁÑ¥½¹}±…‰•°¡½ÁÑ¥½¹}±½½­ÕÁm¥Ñ•µ}¥‘t¤°(€€€€€€€€€€€­•äô‰¡…Ñ}½¹Ù•ÉÍ…Ñ¥½¹}Í•±•Ñ½Èˆ°(€€€€€€€€¤((€€€¥˜¹½ĞÁÉ½µÁĞè(€€€€€€€É•ÑÕÉ¸((€€€µ•ÍÍ…•Ì¹…ÁÁ•¹¡ì‰É½±”ˆè€‰ÕÍ•Èˆ°€‰½¹Ñ•¹ĞˆèÁÉ½µÁÑô¤(€€€¥˜½¹Ù•ÉÍ…Ñ¥½¸¹•Ğ ‰Ñ¥Ñ±”ˆ¤€ôô€‹šZÃ–¾ç¢¾tˆè(€€€€€€€½¹Ù•ÉÍ…Ñ¥½¹l‰Ñ¥Ñ±”‰t€ô}¡…Ñ}Ñ¥Ñ±”¡ÁÉ½µÁĞ¤(€€€½¹Ù•ÉÍ…Ñ¥½¹l‰ÕÁ‘…Ñ•‘}…Ğ‰t€ô‘…Ñ•Ñ¥µ”¹¹½Ü ¤¹¥Í½™½Éµ…Ğ¡Ñ¥µ•ÍÁ•Œô‰Í•½¹‘Ìˆ¤(€€€Í…Ù•}¡…Ñ}¡¥ÍÑ½Éä¡¡¥ÍÑ½Éä¤(€€€İ¥Ñ µ•ÍÍ…•Í}İ¥¹‘½Üè(€€€€€€€İ¥Ñ ÍĞ¹¡…Ñ}µ•ÍÍ…” ‰ÕÍ•Èˆ¤è(€€€€€€€€€€€ÍĞ¹µ…É­‘½İ¸¡ÁÉ½µÁĞ¤((€€€¥˜¹½Ğ½¹™¥œ¹•¹…‰±•è(€€€€€€€…¹Íİ•È€ô€‹–Âkšr«¦7ö»–>¿R£j–’Ÿš¢‡–z/¢¾ß¦'š.§’úo–êS–V¾ò3–æÛ¢ºûö»nã–êSjA$-•äƒÎïî:¿–Š–>c¦?ˆ(€€€•±Í”è(€€€€€€€ÍåÍÑ•µ}ÁÉ½µÁĞ€ô€ (€€€€€€€€€€€€‹’öƒšb¿R×–*oÎïîšö»šÖ¢º‡º_šfë¢÷’öO¾ò3’æšb¿¢C–ş’â—¢Â£j’â·šZš*šr¿–*§š&/ˆ(€€€€€€€€€€€€‹’òc–#–n{¶Sšö»šÖ¢º‡º_5QA=]KAeA=]KšRÛšVo¢¾+šZ·¢şC¢†3ê›šv–J3º_’ú/šVÃš6»¦^»¦Šcˆ(€€€€€€€€€€€€‹–n{¶S–êS–#îgîO¢ºë¾ò3–7¢¦+’úwš6»¾òo’â7†»–ºkš^Ûšb;†»¢¾Óšb;¾ò3’â7–ú_ò[¦ƒ¢º‡º_îOšzsˆ(€€€€€€€€€€€€‹¢.—š>C’úo’êšr¢şG’âš²‡¢º‡º_îOšzs’â+’â/šZ¾ò3–êS–òWR£–Û’â·j–ß’öO’ê/–º{–n{¶Sˆ(€€€€€€€€¤(€€€€€€€É•Á½ÉÑ}½¹Ñ•áĞ€ô}±…Ñ•ÍÑ}É•Á½ÉÑ}½¹Ñ•áĞ ¤(€€€€€€€¥˜É•Á½ÉÑ}½¹Ñ•áĞè(€€€€€€€€€€€ÍåÍÑ•µ}ÁÉ½µÁĞ€¬ô€‰q»šr¢şG’âš²‡šö»šÖ¢º‡º_îOšzs’â+’â/šZ¾òiq¸ˆ€¬©Í½¸¹‘ÕµÁÌ (€€€€€€€€€€€€€€€É•Á½ÉÑ}½¹Ñ•áĞ°(€€€€€€€€€€€€€€€•¹ÍÕÉ•}…Í¥¤õ…±Í”°(€€€€€€€€€€€€€€€‘•™…Õ±ĞõÍÑÈ°(€€€€€€€€€€€€¤(€€€€€€€İ¥Ñ µ•ÍÍ…•Í}İ¥¹‘½Üè(€€€€€€€€€€€İ¥Ñ ÍĞ¹¡…Ñ}µ•ÍÍ…” ‰…ÍÍ¥ÍÑ…¹Ğˆ¤è(€€€€€€€€€€€€€€€İ¥Ñ ÍĞ¹ÍÁ¥¹¹•È ‹š¶–r£šw¢¸¸¸ˆ¤è(€€€€€€€€€€€€€€€€€€€É•ÍÕ±Ğ€ô115±¥•¹Ğ¡½¹™¥œ¤¹¡…Ñ}Ñ•áĞ (€€€€€€€€€€€€€€€€€€€€€€€µ•ÍÍ…•Íl´ÈÀét°(€€€€€€€€€€€€€€€€€€€€€€€ÍåÍÑ•µ}ÁÉ½µÁĞõÍåÍÑ•µ}ÁÉ½µÁĞ°(€€€€€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€€€€€€€€¥˜É•ÍÕ±Ğ¹•Ğ ‰•ÉÉ½Èˆ¤è(€€€€€€€€€€€€€€€€€€€€€€€…¹Íİ•È€ô˜‹š¢‡–z/¢ÂR£–’Ç¢Ò—¾òiíÉ•ÍÕ±Ñl•ÉÉ½Èuôˆ(€€€€€€€€€€€€€€€€€€€•±Í”è(€€€€€€€€€€€€€€€€€€€€€€€…¹Íİ•È€ôÍÑÈ¡É•ÍÕ±Ğ¹•Ğ ‰½¹Ñ•¹Ğˆ¤½È€‹š¢‡–z/šÊ‡šr'¢şS–n{šr'šV#––ºç¾ò3¢¾ß¢7–B;¦7¢¾Wˆ¤(€€€€€€€€€€€€€€€€€€€ÍĞ¹µ…É­‘½İ¸¡…¹Íİ•È¤(€€€€€€€µ•ÍÍ…•Ì¹…ÁÁ•¹¡ì‰É½±”ˆè€‰…ÍÍ¥ÍÑ…¹Ğˆ°€‰½¹Ñ•¹Ğˆè…¹Íİ•Éô¤(€€€€€€€½¹Ù•ÉÍ…Ñ¥½¹l‰ÕÁ‘…Ñ•‘}…Ğ‰t€ô‘…Ñ•Ñ¥µ”¹¹½Ü ¤¹¥Í½™½Éµ…Ğ¡Ñ¥µ•ÍÁ•Œô‰Í•½¹‘Ìˆ¤(€€€€€€€Í…Ù•}¡…Ñ}¡¥ÍÑ½Éä¡¡¥ÍÑ½Éä¤(€€€€€€€É•ÑÕÉ¸((€€€İ¥Ñ µ•ÍÍ…•Í}İ¥¹‘½Üè(€€€€€€€İ¥Ñ ÍĞ¹¡…Ñ}µ•ÍÍ…” ‰…ÍÍ¥ÍÑ…¹Ğˆ¤è(€€€€€€€€€€€ÍĞ¹İ…É¹¥¹œ¡…¹Íİ•È¤(€€€µ•ÍÍ…•Ì¹…ÁÁ•¹¡ì‰É½±”ˆè€‰…ÍÍ¥ÍÑ…¹Ğˆ°€‰½¹Ñ•¹Ğˆè…¹Íİ•Éô¤(€€€½¹Ù•ÉÍ…Ñ¥½¹l‰ÕÁ‘…Ñ•‘}…Ğ‰t€ô‘…Ñ•Ñ¥µ”¹¹½Ü ¤¹¥Í½™½Éµ…Ğ¡Ñ¥µ•ÍÁ•Œô‰Í•½¹‘Ìˆ¤(€€€Í…Ù•}¡…Ñ}¡¥ÍÑ½Éä¡¡¥ÍÑ½Éä¤(()‘•˜µ…¥¸ ¤€´ø9½¹”è(€€€¥¹©•Ñ}ÍÌ ¤(€€€•¹ÍÕÉ•}©½‰}ÍÑ…Ñ” ¤(€€€É•¹‘•É}¡•…‘•È ¤(€€€½¹ÑÉ½±Ì€ôÉÕ¹}½¹ÑÉ½±Ì ¤((€€€¡…Ñ}Ñ…ˆ°…±Õ±…Ñ¥½¹}Ñ…ˆ€ôÍĞ¹Ñ…‰Ì¡l‹šfë¢÷¦^»¶Pˆ°€‹šö»šÖ¢º‡º_’â;îOšzp‰t¤(€€€İ¥Ñ ¡…Ñ}Ñ…ˆè(€€€€€€€É•¹‘•É}¡…Ğ¡½¹ÑÉ½±Ì¤((€€€İ¥Ñ …±Õ±…Ñ¥½¹}Ñ…ˆè(€€€€€€€¥˜½¹ÑÉ½±Íl‰•¹¥¹”‰t€ôô€‰µ…ÑÁ½İ•Èˆ…¹¹½ĞA…Ñ ¡U1Q}5QA=]I}AQ ¤¹•á¥ÍÑÌ ¤è(€€€€€€€€€€€ÍĞ¹•ÉÉ½È¡˜‰5QA=]K¦îc¢º“¢Ş¿–ú’â7–¶c–r£¾òiíU1Q}5QA=]I}AQ!ôˆ¤(€€€€€€€•±Í”è(€€€€€€€€€€€¥˜½¹ÑÉ½±Íl‰ÉÕ¹}±¥­•‰tè(€€€€€€€€€€€€€€€¥˜½¹ÑÉ½±Íl‰…Í•}Á…Ñ ‰t¥Ì9½¹”è(€€€€€€€€€€€€€€€€€€€ÍĞ¹İ…É¹¥¹œ ‹¢¾ß–#¦'š.§š"[’â+’òƒ’â’â«º_’ú/šZ’îÛˆ¤(€€€€€€€€€€€€€€€•±¥˜¹½ĞA…Ñ ¡½¹ÑÉ½±Íl‰…Í•}Á…Ñ ‰t¤¹•á¥ÍÑÌ ¤è(€€€€€€€€€€€€€€€€€€€ÍĞ¹•ÉÉ½È¡˜‹º_’ú/šZ’îÛ’â7–¶c–r£¾òií½¹ÑÉ½±Íl…Í•}Á…Ñ uôˆ¤(€€€€€€€€€€€€€€€•±Í”è(€€€€€€€€€€€€€€€€€€€ÍÑ…ÉÑ}‰…­É½Õ¹‘}©½ˆ¡½¹ÑÉ½±Ì¤(€€€€€€€€€€€€€€€€€€€ÍĞ¹ÍÕ•ÍÌ ‹¢º‡º_’îï–*‡–ŞË–B¿–*£–>¿’î—
ç–ïŠs–"ßšZÃ¢º‡º_*ÛšŠwš~—r/¢şo–ê›¾ò3š"[
ç–ïŠs–>[šÚ#¢º‡º_Šwî#š¶‹ˆ¤(€€€€€€€€€€€€€€€€€€€ÍĞ¹É•ÉÕ¸ ¤((€€€€€€€€€€€É•¹‘•É}±¥Ù•}…É•„ ¤(€€€€€€€€€€€¥˜¹½ĞÍĞ¹Í•ÍÍ¥½¹}ÍÑ…Ñ”¹•Ğ ‰ÉÕ¹¹¥¹}©½ˆˆ¤…¹¹½ĞÍĞ¹Í•ÍÍ¥½¹}ÍÑ…Ñ”¹•Ğ ‰±…ÍÑ}™¥¹¥Í¡•‘}½ÕÑ}‘¥Èˆ¤è(€€€€€€€€€€€€€€€¥¹™½}Á…¹•° (€€€€€€€€€€€€€€€€€€€€‹¢¾ß¢úO–—šö»šÖ¢º‡º_š†#’ú,ˆ°(€€€€€€€€€€€€€€€€€€€€‹¢¾ß–r£–Ş›’úŸ¦'š.§º_’ú/šv—šêC–në–ºkšÆ¢–f£–J3–’Ÿš¢‡–z/¢ºûö»¾ò3Û–B;
ç–ïŠs–ò–/¢şC¢†3šö»šÖšfë¢÷’öOŠwˆ°(€€€€€€€€€€€€€€€€€€€mt°(€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€ÍĞ¹‘¥Ù¥‘•È ¤(€€€€€€€€€€€É•¹‘•É}¡¥ÍÑ½Éå}µ…¹…•È ¤(()¥˜}}¹…µ•}|€ôô€‰}}µ…¥¹}|ˆè(€€€µ…¥¸ ¤(
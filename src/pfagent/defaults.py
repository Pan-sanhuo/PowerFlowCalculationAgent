from __future__ import annotations

from pathlib import Path


DEFAULT_MATPOWER_PATH = r"D:\Program Files\MATLAB\matpower8.1"


def default_matpower_path() -> Path:
    return Path(DEFAULT_MATPOWER_PATH)


def matpower_data_dir(matpower_path: str | Path | None = None) -> Path:
    root = Path(matpower_path or DEFAULT_MATPOWER_PATH)
    return root / "data"


def resolve_matpower_case(case_name: str, matpower_path: str | Path | None = None) -> Path:
    name = case_name.strip()
    if name.lower().startswith("matpower:"):
        name = name.split(":", 1)[1].strip()
    if not name.lower().endswith(".m"):
        name = f"{name}.m"
    return matpower_data_dir(matpower_path) / name


MATPOWER_BUILTIN_CASES = [
    "case9",
    "case14",
    "case30",
    "case39",
    "case57",
    "case118",
    "case300",
]

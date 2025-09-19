# src/external/challan_loader.py
from __future__ import annotations
import os, importlib.util, types
from functools import lru_cache
from typing import Optional

_ENV_KEYS = ("CHALLAN_APP_DIR", "CHAILLAN_APP_DIR")  # 오탈자도 허용

def _env_dir() -> str:
    raw = next((os.getenv(k) for k in _ENV_KEYS if os.getenv(k)), None)
    if not raw:
        raise RuntimeError(
            'CHALLAN_APP_DIR is not set.\n'
            'Example:\n  CHALLAN_APP_DIR="/absolute/path/to/internship_challan_app"'
        )
    # 따옴표/공백/ ~ /$VAR 처리
    val = raw.strip().strip('\'"')
    val = os.path.expanduser(os.path.expandvars(val))
    if not os.path.isdir(val):
        raise RuntimeError(f"CHALLAN_APP_DIR does not exist: {val}")
    return val

def _load_module_from_filename(filename: str, mod_name: str) -> types.ModuleType:
    base = _env_dir()
    py_path = os.path.join(base, filename)
    if not os.path.isfile(py_path):
        raise FileNotFoundError(f"{filename} not found in CHALLAN_APP_DIR: {py_path}")
    spec = importlib.util.spec_from_file_location(mod_name, py_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load spec for {py_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod

@lru_cache(maxsize=1)
def load_challan_postprocessing() -> types.ModuleType:
    # 폴더 안에 challan_postprocessing.py 가 있어야 함
    return _load_module_from_filename("challan_postprocessing.py", "challan_postprocessing")

@lru_cache(maxsize=1)
def load_fit_ellipse() -> Optional[types.ModuleType]:
    # 있으면 로드, 없으면 None
    try:
        return _load_module_from_filename("fit_ellipse.py", "fit_ellipse")
    except FileNotFoundError:
        return None

# src/external/challan_loader.py
from __future__ import annotations
import os, importlib.util, types
from functools import lru_cache
from typing import Optional

ENV_KEY = "CHALLAN_APP_DIR"

def _load_module_from_path(py_path: str, mod_name: str) -> types.ModuleType:
    if not os.path.isfile(py_path):
        raise FileNotFoundError(f"External module not found: {py_path}")
    spec = importlib.util.spec_from_file_location(mod_name, py_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load spec for {py_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod

@lru_cache(maxsize=1)
def load_challan_postprocessing() -> types.ModuleType:
    base = os.environ.get(ENV_KEY)
    if not base:
        raise RuntimeError(
            f"{ENV_KEY} is not set. Example:\n"
            f'export {ENV_KEY}="/Users/juntk/Desktop/Astronomical Research Institute Data/Data/challan_loader"'
        )
    return _load_module_from_path(
        os.path.join(base, "challan_postprocessing.py"),
        "challan_postprocessing",
    )

@lru_cache(maxsize=1)
def load_fit_ellipse() -> Optional[types.ModuleType]:
    """옵션: fit_ellipse.py가 있으면 로드(없어도 서비스는 동작)"""
    base = os.environ.get(ENV_KEY)
    if not base:
        return None
    path = os.path.join(base, "fit_ellipse.py")
    if not os.path.isfile(path):
        return None
    return _load_module_from_path(path, "fit_ellipse")

from __future__ import annotations
import uuid
from typing import Dict, Any, Optional
import numpy as np
from astropy.io import fits

from src.external.challan_loader import load_challan_postprocessing, load_fit_ellipse

# 전역 캐시: 항상 1개만 유지
_FILE_REG: Dict[str, Dict[str, Any]] = {}

# ---------------- Register / Meta ----------------
def register_fits(path: str) -> tuple[str, tuple[int, ...] | None, dict[str, Any]]:
    """FITS 파일을 등록 (기존 캐시는 모두 삭제)"""
    with fits.open(path, memmap=False, do_not_scale_image_data=True) as hdul:  # 🔥 memmap 끔
        arr = hdul[0].data
        shape = tuple(arr.shape) if arr is not None else None
        header = dict(hdul[0].header) if hdul[0].header else {}

    # 🔥 이전 캐시 제거 (한 번에 하나만)
    _FILE_REG.clear()

    file_id = str(uuid.uuid4())
    _FILE_REG[file_id] = {
        "path": path,
        "shape": shape,
        "header": header,
        "cube": np.asarray(arr, dtype=np.float32) if arr is not None else None,
    }
    return file_id, shape, header

def get_meta(file_id: str) -> dict[str, Any]:
    if file_id not in _FILE_REG:
        raise KeyError(f"Unknown file_id {file_id}")
    return _FILE_REG[file_id]

# ---------------- External algorithms ----------------
def _apply_dark_flat_via_external(data: np.ndarray) -> np.ndarray:
    chl_mod = load_challan_postprocessing()
    if hasattr(chl_mod, "challan_postprocessing"):
        chl = chl_mod.challan_postprocessing()
        if hasattr(chl, "apply_dark_flat"):
            return chl.apply_dark_flat(data)
    if hasattr(chl_mod, "apply_dark_flat"):
        return chl_mod.apply_dark_flat(data)
    return data

def _correct_slit_curvature_via_external(slit2d: np.ndarray) -> np.ndarray:
    fit_mod = load_fit_ellipse()
    if fit_mod is not None and hasattr(fit_mod, "make_circular"):
        try:
            return fit_mod.make_circular(slit2d)
        except TypeError:
            return fit_mod.make_circular(slit2d, 0.0, (slit2d.shape[1]/2, slit2d.shape[0]/2))
    return slit2d

# ---------------- Public APIs ----------------
from io import BytesIO
from PIL import Image

def _to_png(arr2d: np.ndarray, max_wh: int = 1024, *, percent_clip: float = 1.0):
    arr = np.nan_to_num(arr2d, nan=0.0, posinf=0.0, neginf=0.0)

    if percent_clip > 0:
        vmin, vmax = np.percentile(arr, (1.0, 99.0))
        if vmax <= vmin:
            vmax = vmin + 1.0
        arr = np.clip(arr, vmin, vmax)
    else:
        vmin, vmax = float(np.min(arr)), float(np.max(arr))
        if vmax <= vmin:
            vmin, vmax = 0.0, 1.0

    u8 = ((arr - vmin) / (vmax - vmin) * 255).astype(np.uint8)
    im = Image.fromarray(u8, mode="L")

    h, w = im.height, im.width
    scale = min(1.0, max_wh / max(h, w))
    if scale < 1.0:
        im = im.resize((int(w * scale), int(h * scale)), Image.BILINEAR)
    buf = BytesIO(); im.save(buf, format="PNG"); buf.seek(0)
    return buf.getvalue(), im.width, im.height

def load_preview(file_id: str, z: Optional[int] = None, *, percent_clip: float = 1.0, apply_correction: bool = True):
    meta = get_meta(file_id)
    cube = meta["cube"]
    if cube is None:
        raise ValueError("No cube loaded")

    if cube.ndim == 3:
        z = cube.shape[0] // 2 if z is None else int(np.clip(z, 0, cube.shape[0]-1))
        arr2d = cube[z]
    else:
        arr2d = cube

    if apply_correction:
        arr2d = _apply_dark_flat_via_external(arr2d)

    return _to_png(arr2d, percent_clip=percent_clip)

def get_slit_image(file_id: str, x: int, *, percent_clip: float = 1.0, apply_correction: bool = True):
    meta = get_meta(file_id)
    cube = meta["cube"]
    if cube is None or cube.ndim != 3:
        raise ValueError("3D cube required")

    data = _apply_dark_flat_via_external(cube) if apply_correction else cube
    slit = data[:, :, x].T   # (z, y) → 전치 → (y, z)
    slit = _correct_slit_curvature_via_external(slit)
    return _to_png(slit, percent_clip=percent_clip)

def get_spectrum(file_id: str, x: int, y: int, *, apply_correction: bool = True):
    meta = get_meta(file_id)
    cube = meta["cube"]
    if cube is None or cube.ndim != 3:
        raise ValueError("3D cube required")

    data = _apply_dark_flat_via_external(cube) if apply_correction else cube
    spec = data[:, y, x].astype(np.float32)
    lam = np.arange(spec.size, dtype=np.float32)
    return lam, spec

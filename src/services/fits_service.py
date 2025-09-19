# src/services/fits_service.py
from __future__ import annotations
import uuid
from typing import Dict, Any, Optional
import numpy as np
from astropy.io import fits
from io import BytesIO
from PIL import Image

from src.external.challan_loader import load_challan_postprocessing, load_fit_ellipse

_FILE_REG: Dict[str, Dict[str, Any]] = {}

# ---------------- Register / Meta ----------------
def register_fits(path: str) -> tuple[str, tuple[int, ...] | None, dict[str, Any]]:
    """FITS 파일 등록: 첫 번째 데이터가 있는 IMAGE HDU 자동 선택"""
    with fits.open(path, memmap=False, do_not_scale_image_data=True) as hdul:
        hdu = next((h for h in hdul if getattr(h, "data", None) is not None), None)
        if hdu is None:
            raise ValueError("No IMAGE HDU with data")
        arr = hdu.data
        shape = tuple(arr.shape) if arr is not None else None
        header = dict(hdu.header) if hdu.header else {}

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

# ---------------- New: Z 슬라이스 자동 추정 ----------------
def guess_best_z(file_id: str, target: int = 512) -> int:
    """
    신호가 가장 잘 보일 만한 슬라이스를 추정.
    각 z 평면의 분산(variance)을 대략 계산해 최댓값 z를 반환.
    큰 이미지를 빠르게 처리하기 위해 다운샘플링 후 계산.
    """
    meta = get_meta(file_id)
    cube = meta["cube"]
    if cube is None or cube.ndim != 3:
        return 0
    Z, Y, X = cube.shape
    step_y = max(1, Y // target)
    step_x = max(1, X // target)
    small = cube[:, ::step_y, ::step_x]
    # NaN 무시 분산
    var = np.nanvar(small, axis=(1, 2))
    # 모두 동일하면 0으로 귀결
    if not np.isfinite(var).any():
        return 0
    return int(np.nanargmax(var))

# ---------------- External algorithms (fail-soft) ----------------
def _apply_dark_flat_via_external(data: np.ndarray) -> np.ndarray:
    try:
        chl_mod = load_challan_postprocessing()
        if hasattr(chl_mod, "challan_postprocessing"):
            chl = chl_mod.challan_postprocessing()
            if hasattr(chl, "apply_dark_flat"):
                return chl.apply_dark_flat(data)
        if hasattr(chl_mod, "apply_dark_flat"):
            return chl_mod.apply_dark_flat(data)
    except Exception as e:
        print(f"[postproc skipped] {type(e).__name__}: {e}")
    return data

def _correct_slit_curvature_via_external(slit2d: np.ndarray) -> np.ndarray:
    try:
        fit_mod = load_fit_ellipse()
        if fit_mod is not None and hasattr(fit_mod, "make_circular"):
            try:
                return fit_mod.make_circular(slit2d)
            except TypeError:
                return fit_mod.make_circular(slit2d, 0.0, (slit2d.shape[1]/2, slit2d.shape[0]/2))
    except Exception as e:
        print(f"[curvature skipped] {type(e).__name__}: {e}")
    return slit2d

# ---------------- PNG helpers ----------------
def _to_png(arr2d: np.ndarray, max_wh: int = 1024, *, percent_clip: float = 1.0):
    arr = np.nan_to_num(arr2d, nan=0.0, posinf=0.0, neginf=0.0)

    # robust stretch: p1/p99가 비정상이면 min/max로 폴백
    if percent_clip > 0:
        p1, p99 = np.percentile(arr, (1.0, 99.0))
        if (not np.isfinite(p1)) or (not np.isfinite(p99)) or (p99 - p1) < 1e-6:
            vmin, vmax = float(np.min(arr)), float(np.max(arr))
        else:
            vmin, vmax = float(p1), float(p99)
        arr = np.clip(arr, vmin, vmax)
    else:
        vmin, vmax = float(np.min(arr)), float(np.max(arr))
        if vmax <= vmin:
            vmin, vmax = 0.0, 1.0

    denom = (vmax - vmin) if (vmax - vmin) != 0 else 1.0
    u8 = ((arr - vmin) / denom * 255.0).astype(np.uint8)
    im = Image.fromarray(u8, mode="L")

    h, w = im.height, im.width
    scale = min(1.0, max_wh / max(h, w))
    if scale < 1.0:
        im = im.resize((int(w * scale), int(h * scale)), Image.BILINEAR)
    buf = BytesIO(); im.save(buf, format="PNG"); buf.seek(0)
    return buf.getvalue(), im.width, im.height

# ---------------- Public APIs ----------------
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
        arr_corr = _apply_dark_flat_via_external(arr2d)
        if isinstance(arr_corr, np.ndarray) and arr_corr.shape == arr2d.shape:
            arr2d = arr_corr
        else:
            print("[warn] correction returned invalid result; using original")

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

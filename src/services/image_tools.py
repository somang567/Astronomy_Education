# src/services/_image_tools.py
from __future__ import annotations
import numpy as np
from PIL import Image
from io import BytesIO
from typing import Tuple

def to_png_bytes(arr2d: np.ndarray, max_wh: int = 1024, percent_clip: float = 1.0) -> Tuple[bytes, int, int, dict]:
    """
    2D array → PNG 바이트 + (w,h) + 통계
    """
    arr = np.nan_to_num(arr2d, nan=0.0, posinf=0.0, neginf=0.0)

    if percent_clip > 0:
        p1, p99 = np.percentile(arr, (1.0, 99.0))
        if not np.isfinite(p1) or not np.isfinite(p99) or (p99 - p1) < 1e-6:
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

    stats = {"vmin": vmin, "vmax": vmax, "mean": float(arr.mean()), "std": float(arr.std())}
    buf = BytesIO(); im.save(buf, format="PNG"); buf.seek(0)
    return buf.getvalue(), im.width, im.height, stats

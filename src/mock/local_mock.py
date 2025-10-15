# src/mock/local_mock.py
from __future__ import annotations
from datetime import datetime
import os
import uuid
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from flask import Blueprint, jsonify, request, send_file, abort, url_for

from ..utils.nameparse import parse_stem  # 파일명(stem) → 날짜/메타 파싱

# ── 이미지/스펙트럼 계산 의존성 ────────────────────────────────────────────────
#  PNG → numpy
from PIL import Image
import numpy as np

#  FITS/WCS → 파장축 계산
from astropy.io import fits
from astropy.wcs import WCS


mock_bp = Blueprint("mock", __name__, url_prefix="/dev")

# 인메모리 인덱스: stem -> { file_id_hex, fits_path, pngs[], meta{...} }
_INDEX: Dict[str, Dict] = {}
_LAST = {"png_dir": None, "fits_dir": None}


# ── 경로 읽기 (.env) ─────────────────────────────────────────────────────────
def _env_paths() -> Tuple[Path, Path]:
    """
    .env 예시:
      LOCAL_PNG_DIR="/path/to/Fits_png_TimeData"
      LOCAL_FITS_DIR="/path/to/Fits_OriginalData"
    """
    png = Path(os.getenv("LOCAL_PNG_DIR", "").strip())
    fits_dir = Path(os.getenv("LOCAL_FITS_DIR", "").strip())
    return png, fits_dir


# ── 인덱스 스캔 ───────────────────────────────────────────────────────────────
def _scan(force: bool = False) -> None:
    """
    PNG/FITS를 훑어서 인메모리 인덱스(_INDEX)를 구성한다.
      - PNG가 있으면 그 stem을 기준으로 등록하고, 동일 stem FITS를 우선 매칭
      - 동일 stem 매칭 실패 시, 파일명에서 파싱한 타임스탬프(YYYYMMDD_HHMMSS)로
        FITS 후보를 찾아 '유일 후보'일 때만 보조 매칭
      - PNG가 전혀 없어도 FITS만 있는 항목은 frames=0으로 별도 등록
    """
    png_dir, fits_dir = _env_paths()

    # 디렉토리 변경 없이 기존 인덱스가 있고 force가 아니면 skip
    if (
        not force
        and _LAST["png_dir"] == str(png_dir)
        and _LAST["fits_dir"] == str(fits_dir)
        and _INDEX
    ):
        return

    _INDEX.clear()
    _LAST.update({"png_dir": str(png_dir), "fits_dir": str(fits_dir)})

    # 1) FITS stem 수집
    fits_map: Dict[str, Path] = {}
    if fits_dir.exists():
        for p in fits_dir.rglob("*"):
            if p.suffix.lower() in {".fits", ".fts", ".fit"}:
                fits_map[p.stem] = p

    # 2) PNG stem → 파일들
    png_groups: Dict[str, List[Path]] = {}
    if png_dir.exists():
        for p in png_dir.rglob("*.png"):
            png_groups.setdefault(p.stem, []).append(p)

    # 3) PNG가 있는 stem 우선 등록
    for stem, arr in png_groups.items():
        meta = parse_stem(stem)
        if not meta:
            # 파일명 규칙이 맞지 않으면 스킵 (원하면 여기서 느슨한 파서로 보강 가능)
            continue

        arr.sort()  # 프레임 순서 보장

        # ① 기본: 동일 stem으로 FITS 매칭
        fpath: Optional[Path] = fits_map.get(stem)

        # ② 기본 매칭 실패 시: 타임스탬프 기반 보조 매칭 (유일 후보일 때만)
        if not fpath and meta.get("dt"):
            ts = meta["dt"].strftime("%Y%m%d_%H%M%S")  # 예: 20241017_043512
            candidates = [k for k in fits_map.keys() if ts in k]
            if len(candidates) == 1:
                fpath = fits_map[candidates[0]]

        # 안정적 파일 ID (앱 재시작해도 동일)
        fid = uuid.uuid5(uuid.NAMESPACE_URL, f"mock:{stem}").hex

        _INDEX[stem] = {
            "file_id_hex": fid,
            "fits_path": str(fpath) if fpath else None,
            "pngs": [str(p) for p in arr],
            "meta": {
                "stem": stem,
                "datetime": meta["dt"].isoformat(),  # "YYYY-MM-DDTHH:MM:SS.ssssss"
                "instrument": None,
                "exptime": None,
                "frames": len(arr),
            },
        }

    # 4) PNG가 아예 없는 FITS도 추가 (frames=0, thumb 없음)
    for stem, fpath in fits_map.items():
        if stem in _INDEX:
            continue
        meta = parse_stem(stem)
        dt_iso = meta["dt"].isoformat() if (meta and meta.get("dt")) else ""
        fid = uuid.uuid5(uuid.NAMESPACE_URL, f"mock:{stem}").hex
        _INDEX[stem] = {
            "file_id_hex": fid,
            "fits_path": str(fpath),
            "pngs": [],
            "meta": {
                "stem": stem,
                "datetime": dt_iso,  # 없으면 빈 문자열
                "instrument": None,
                "exptime": None,
                "frames": 0,
            },
        }



# ── 유틸: 스펙트럼 계산 (PNG/FITS) ───────────────────────────────────────────
def _spectrum_from_png(
    png_path: str, y: Optional[int] = None, h: int = 5
) -> Tuple[List[int], List[float], Dict]:
    """
    PNG 이미지를 열어 x-축 스펙트럼(픽셀 vs intensity)을 만든다.
    y: 중심 y 픽셀(미지정 시 중앙), h: ±h 합(총 2h+1 행)
    """
    img = Image.open(png_path).convert("L")  # grayscale
    arr = np.asarray(img, dtype=np.float32)  # (H, W)
    H, W = arr.shape
    if y is None:
        y = H // 2
    y0 = max(0, y - h)
    y1 = min(H, y + h + 1)
    band = arr[y0:y1, :]  # (rows, W)
    spec = band.sum(axis=0)  # (W,)

    # 보기 좋게 정규화
    if spec.max() > 0:
        spec = spec / spec.max()

    x = np.arange(W, dtype=int).tolist()
    yvals = spec.astype(float).tolist()
    return x, yvals, {"height": H, "width": W, "y0": y0, "y1": y1}


def _wavelength_axis_from_header(hdr, length: int) -> Tuple[Optional[List[float]], Optional[str]]:
    """
    FITS header에서 1축 파장 보정 정보를 뽑아 λ 배열 생성.
    우선순위: ① WCS → ② 선형(CRVAL1/CDELT1(or CD1_1)/CRPIX1) → 실패 시 (None, None)
    """
    # ① WCS 시도
    try:
        w = WCS(hdr)
        pix = np.arange(length, dtype=float)
        # y=0 고정, x만 스캔 (2D 가정)
        world = w.all_pix2world(np.vstack([pix, np.zeros_like(pix)]).T, 0)
        lam = np.asarray(world[:, 0], dtype=float)
        unit = hdr.get("CUNIT1") or "unknown"
        if np.isfinite(lam).all() and lam.ptp() > 0:
            return lam.tolist(), unit
    except Exception:
        pass

    # ② 선형 해상(표준 키워드)
    try:
        crval = float(hdr.get("CRVAL1"))
        cdelt = hdr.get("CDELT1")
        if cdelt is None:
            cdelt = hdr.get("CD1_1")
        cdelt = float(cdelt)
        crpix = float(hdr.get("CRPIX1", 1.0))
        x = np.arange(length, dtype=float) + 1.0  # FITS는 1-indexed
        lam = crval + (x - crpix) * cdelt
        unit = hdr.get("CUNIT1") or "unknown"
        if np.isfinite(lam).all() and lam.ptp() > 0:
            return lam.tolist(), unit
    except Exception:
        pass

    return None, None


def _spectrum_from_fits(
    fits_path: str, hdu_index: Optional[int] = None, y: Optional[int] = None, h: int = 5
) -> Tuple[List[float], List[float], Dict]:
    """
    FITS를 열어 x-축 방향 1D 스펙트럼을 λ로 변환해 반환.
    - 이미지형(2D/3D) 스펙트럼을 가정 (3D면 첫 프레임 사용)
    - λ 축은 WCS 또는 CRVAL1/CD1_1/CRPIX1 기반
    반환: (lambda(list), flux(list), meta(dict))
    """
    with fits.open(fits_path, memmap=True) as hdul:
        # 이미지 HDU 선택
        if (
            hdu_index is not None
            and 0 <= hdu_index < len(hdul)
            and getattr(hdul[hdu_index], "data", None) is not None
        ):
            hdu = hdul[hdu_index]
        else:
            hdu = next(
                (h for h in hdul if getattr(h, "data", None) is not None and h.data.ndim >= 2),
                None,
            )
            if hdu is None:
                raise ValueError("No image HDU found in FITS")

        data = hdu.data
        hdr = hdu.header

        # 2D/3D 처리
        if data.ndim == 3:
            img = np.asarray(data[0], dtype=np.float32)  # 첫 프레임
        else:
            img = np.asarray(data, dtype=np.float32)

        H, W = img.shape[-2], img.shape[-1]
        if y is None:
            y = H // 2
        y0 = max(0, y - h)
        y1 = min(H, y + h + 1)
        band = img[y0:y1, :]  # (rows, W)
        flux = band.sum(axis=0)  # (W,)

        # 파장축
        lam, unit = _wavelength_axis_from_header(hdr, W)
        lam_is_wavelength = lam is not None
        if lam is None:
            lam = np.arange(W, dtype=float).tolist()
            unit = "pixel"

        # 보기 좋게 정규화
        f = flux.astype(float)
        m = np.nanmax(f)
        if m > 0:
            f = f / m

        meta = {
            "height": H,
            "width": W,
            "y0": y0,
            "y1": y1,
            "wavelength_unit": unit,
            "x_is_wavelength": bool(lam_is_wavelength),
            "hdu_index": getattr(hdu, "index", None),
        }
        return lam, f.tolist(), meta


# ── API: 관리/검색/파일/스펙트럼 ──────────────────────────────────────────────
@mock_bp.get("/debug_paths")
def debug_paths():
    png_dir, fits_dir = _env_paths()
    return jsonify(
        {
            "png_dir": str(png_dir),
            "png_exists": png_dir.exists(),
            "fits_dir": str(fits_dir),
            "fits_exists": fits_dir.exists(),
            "index_size": len(_INDEX),
            "sample": next(iter(_INDEX.keys()), None),
        }
    )


@mock_bp.get("/reindex")
def reindex():
    _scan(force=True)
    return jsonify({"stems": len(_INDEX)})


def parse_client_dt(s: str | None):
    """
    클라이언트에서 오는 date_from/date_to 파싱.
    허용: 'YYYY-MM-DD HH:MM[:SS]' 또는 'YYYY-MM-DDTHH:MM[:SS]'
    반환: datetime | None
    실패: 'INVALID'
    """
    if not s:
        return None
    raw = s.strip()
    cand = raw.replace(" ", "T")
    if len(cand) == 16:  # YYYY-MM-DDTHH:MM
        cand += ":00"
    try:
        return datetime.fromisoformat(cand)
    except Exception:
        return "INVALID"

def _parse_iso(s: str | None):
    """ 'YYYY-MM-DDTHH:MM:SS[.ffffff]' 를 datetime으로 파싱 """
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        # 마이크로초가 없는 등 변형을 관대하게 처리하려면 여기에 보정 로직 추가
        return None
    
def _parse_client_dt_strict(s: str | None):
    """
    'YYYY-MM-DD HH:MM[:SS]' 또는 'YYYY-MM-DDTHH:MM[:SS]'만 허용.
    들어왔는데 파싱이 안 되면 None이 아니라 'INVALID'로 돌려서 에러를 낼 수 있게.
    """
    if not s:
        return None
    raw = s.strip()
    cand = raw.replace(" ", "T")
    if len(cand) == 16:  # YYYY-MM-DDTHH:MM
        cand += ":00"
    try:
        return datetime.fromisoformat(cand)
    except Exception:
        return "INVALID"
    
@mock_bp.get("/search")
def search():
    _scan()
    q = (request.args.get("q") or "").lower()
    sort = (request.args.get("sort") or "-observed_at").strip()
    dfv = parse_client_dt(request.args.get("date_from"))
    dtv = parse_client_dt(request.args.get("date_to"))
    if dfv == "INVALID" or dtv == "INVALID":
        abort(400, "Bad date format. Use 'YYYY-MM-DD HH:MM[:SS]' or the calendar.")
    df = dfv if dfv not in (None, "INVALID") else None
    dt = dtv if dtv not in (None, "INVALID") else None

    if df and not dt:
        dt = df.replace(hour=23 , minute=59 , second=59 , microsecond=0)
    rows = []
    for stem, row in _INDEX.items():
        if q and q not in stem.lower():
            continue
        iso = row["meta"].get("datetime", "")  # 'YYYY-MM-DDTHH:MM:SS.ssssss'
        # 문자열 비교 대신 datetime으로 비교 (보다 안전)
        pass_ok = True
        if iso and (df or dt):
            try:
                obs = datetime.fromisoformat(iso)  # PNG 이름에서 파싱된 값
            except Exception:
                obs = None
            if df and obs and obs < df: pass_ok = False
            if dt and obs and obs > dt: pass_ok = False
        if not pass_ok:
            continue

        rows.append(
            {
                "file_id": row["file_id_hex"],
                "filename": (Path(row["fits_path"]).name if row.get("fits_path") else stem + ".fts"),
                "target": stem.split("_")[0],
                "date_obs": iso or None,
                "exptime": row["meta"].get("exptime"),
                "frames": row["meta"].get("frames"),
                "shape": None,
                "flags": (["no_fits"] if not row.get("fits_path") else []),
                "instrument": row["meta"].get("instrument"),
                "thumb_url": (
                    url_for("mock.png_file", file_id=row["file_id_hex"], idx=0)
                    if row.get("pngs")
                    else None
                ),
            }
        )

    key = (sort or "-observed_at").lstrip("-")
    rev = (sort or "-observed_at").startswith("-")
    if key in ("observed_at", "date_obs"):
        rows.sort(key=lambda r: (r["date_obs"] or ""), reverse=rev)
    elif key == "exptime":
        rows.sort(key=lambda r: (r["exptime"] or 0), reverse=rev)
    elif key in ("object", "target"):
        rows.sort(key=lambda r: (r["target"] or ""), reverse=rev)

    return jsonify({"total": len(rows), "items": rows})


@mock_bp.get("/frames/<file_id>")
def frames(file_id: str):
    """
    기존: 같은 stem에 딸린 PNG들만 반환 → 대부분 1프레임
    변경: 같은 '날짜(YYYY-MM-DD)'에 속한 모든 항목을 한 타임라인으로 반환
    - 기준: 요청한 file_id의 meta['datetime']의 날짜 부분
    - 각 항목은 그 stem의 첫 번째 PNG를 대표 프레임으로 사용 (대부분 1장/항목)
    """
    _scan()
    # 기준 stem 찾기
    stem = next((s for s, v in _INDEX.items() if v["file_id_hex"] == file_id), None)
    if not stem:
        abort(404)

    rec = _INDEX[stem]
    dt_iso = rec["meta"].get("datetime")  # "YYYY-MM-DDTHH:MM:SS.ssssss"
    if not dt_iso:
        # 기존 동작(해당 stem의 png만)
        items = [
            {"index": i, "url": url_for("mock.png_file", file_id=file_id, idx=i), "channel": None}
            for i, _ in enumerate(rec.get("pngs") or [])
        ]
        return jsonify({"items": items})

    # 같은 '날짜'의 모든 레코드 수집
    try:
        anchor = datetime.fromisoformat(dt_iso)
    except Exception:
        anchor = None

    def same_date(rec_dt_iso: str) -> bool:
        if not anchor or not rec_dt_iso:
            return False
        try:
            d = datetime.fromisoformat(rec_dt_iso)
            return (d.date() == anchor.date())
        except Exception:
            return False

    # 같은 날짜의 모든 인덱스들을 시간순 정렬
    pool = []
    for s, v in _INDEX.items():
        iso = v["meta"].get("datetime")
        if same_date(iso) and (v.get("pngs") or []):
            pool.append((iso, v))  # iso로 정렬

    pool.sort(key=lambda t: t[0])  # 시간순

    # 각 항목의 첫 이미지를 한 프레임으로 사용
    items = []
    for i, (_, v) in enumerate(pool):
        fid = v["file_id_hex"]
        items.append({
            "index": i,
            "url": url_for("mock.png_file", file_id=fid, idx=0),
            "channel": None
        })

    return jsonify({"items": items})

@mock_bp.get("/png/<file_id>/<int:idx>", endpoint="png_file")
def png_file(file_id: str, idx: int):
    _scan()
    stem = next((s for s, v in _INDEX.items() if v["file_id_hex"] == file_id), None)
    if not stem:
        abort(404)
    lst = _INDEX[stem]["pngs"]
    if idx < 0 or idx >= len(lst):
        abort(404)
    return send_file(lst[idx], mimetype="image/png")

@mock_bp.get("/fits/<file_id>")
def fits_file(file_id: str):
    _scan()
    stem = next((s for s, v in _INDEX.items() if v["file_id_hex"] == file_id), None)
    if not stem:
        abort(404)
    fpath = _INDEX[stem]["fits_path"]
    if not fpath:
        abort(404)
    return send_file(fpath, as_attachment=True)


@mock_bp.get("/spectrum")
def spectrum():
    """
    /dev/spectrum?file_id=...&idx=0&y=...&h=...
      - idx: PNG 프레임 인덱스(현재는 FITS 3D 매핑 없이 무시; 향후 확장 가능)
      - y/h: 세로 합 대역
    FITS가 있으면 FITS 기반 λ-스펙트럼, 없으면 PNG 기반(픽셀축)으로 반환.
    """
    _scan()
    file_id = request.args.get("file_id")
    if not file_id:
        abort(400, "file_id required")

    idx = request.args.get("idx", type=int, default=0)
    y = request.args.get("y", type=int)
    h = request.args.get("h", type=int, default=5)

    stem = next((s for s, v in _INDEX.items() if v["file_id_hex"] == file_id), None)
    if not stem:
        abort(404)

    rec = _INDEX[stem]
    fits_path = rec.get("fits_path")

    try:
        # 1) FITS 우선: λ-스펙트럼
        if fits_path and Path(fits_path).exists():
            lam, flux, meta = _spectrum_from_fits(fits_path, hdu_index=None, y=y, h=h)
            return jsonify({"x": lam, "y": flux, "frame": idx, "meta": meta})

        # 2) PNG fallback: 픽셀축 스펙트럼
        pngs = rec.get("pngs") or []
        if not pngs:
            abort(404, "no png or fits to compute spectrum")
        x, yvals, meta = _spectrum_from_png(pngs[idx], y=y, h=h)
        meta.update({"wavelength_unit": "pixel", "x_is_wavelength": False})
        return jsonify({"x": x, "y": yvals, "frame": idx, "meta": meta})
    except Exception as e:
        abort(500, f"spectrum failed: {type(e).__name__}: {e}")

@mock_bp.get("/diag")
def diag():
    _scan()
    total = len(_INDEX)
    matched = sum(1 for v in _INDEX.values() if v.get("fits_path"))
    unmatched = total - matched
    # 앞부분 10개 샘플만
    sample_unmatched = [
        {
            "stem": s,
            "png_count": len(v.get("pngs") or []),
            "fits_path": v.get("fits_path"),
            "datetime": (v.get("meta") or {}).get("datetime")
        }
        for s, v in list(_INDEX.items())[:10]
        if not v.get("fits_path")
    ]
    sample_matched = [
        {
            "stem": s,
            "fits_basename": Path(v.get("fits_path")).name if v.get("fits_path") else None,
            "png_count": len(v.get("pngs") or [])
        }
        for s, v in list(_INDEX.items())[:10]
        if v.get("fits_path")
    ]
    return jsonify({
        "total": total,
        "matched": matched,
        "unmatched": unmatched,
        "sample_unmatched": sample_unmatched,
        "sample_matched": sample_matched,
    })

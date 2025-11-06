# src/services/fits_ingest_service.py
from __future__ import annotations
import os , uuid , numpy as np
from astropy.io import fits
from typing import Dict, Any, Optional

from src.utils.io_utils import sha256_hex, parse_date_obs, standard_Filename
from src.services.image_tools import to_png_bytes
from src.models import db, FileStorage, FitsFile, FitsHDU, FitsHeaderKeyvalue, PreviewImage

PREVIEW_ROOT = "/home/kasi/KASI_AstroEducation/Fits_png_TimeData"   # 실제 서버 경로에 맞게 설정

def _uuid_bytes() -> bytes:
    return uuid.uuid4().bytes

def register_fits_to_db(path: str, *, instrument_id: Optional[int]=None) -> tuple[str, tuple[int,...], Dict[str,Any]]:
    """
    FITS 파일 1건을 DB에 영속화:
      - file_storage (원본)
      - fits_file
      - fits_hdu(0)
      - (선택) header kv 일부
      - (선택) preview 생성/저장
    반환: (fits_id_hex, shape, header0_dict)
    """
    # 1) FITS 오픈(데이터/헤더 확보)
    with fits.open(path, memmap=False, do_not_scale_image_data=True) as hdul:
        hdu = next((h for h in hdul if getattr(h, "data", None) is not None), None)
        if hdu is None:
            raise ValueError("No IMAGE HDU with data")
        arr = np.asarray(hdu.data)
        hdr0 = dict(hdu.header)
        shape = tuple(arr.shape)

    original_name = os.path.basename(path)
    canonical = standard_Filename(original_name, hdr0)
    observed_at = parse_date_obs(hdr0)

    # 2) 메타 계산
    size = os.path.getsize(path)
    digest = sha256_hex(path)

    # 3) DB 트랜잭션
    fits_bin = _uuid_bytes()
    hdu_bin  = _uuid_bytes()
    file_bin = _uuid_bytes()

    try:
        # file_storage (원본)
        fs = FileStorage(
            file_id=file_bin, file_path=path, media_type="application/fits",
            file_size=size, sha256_hash=digest
        )
        db.session.add(fs)

        # fits_file
        ff = FitsFile(
            fits_id=fits_bin, storage_file_id=file_bin,
            original_filename=original_name, canonical_name=canonical,
            observed_at=observed_at, instrument_id=instrument_id, status="READY"
        )
        db.session.add(ff)

        # fits_hdu(0)
        hdu_row = FitsHDU(
            hdu_id=hdu_bin, fits_id=fits_bin, hdu_index=0, hdu_type="IMAGE",
            bitpix=int(hdr0.get("BITPIX", 16)),
            shape_json=list(arr.shape),     # JSON 컬럼이므로 파이썬 오브젝트 그대로
            header_json={k: (None if v is None else str(v)) for k,v in hdr0.items()}
        )
        db.session.add(hdu_row)

        # header key-values (자주 쓰는 키만)
        if "OBJECT" in hdr0:
            db.session.add(FitsHeaderKeyvalue(fits_id=fits_bin, header_key="OBJECT", value_text=str(hdr0["OBJECT"])))
        if "EXPTIME" in hdr0:
            try:
                db.session.add(FitsHeaderKeyvalue(fits_id=fits_bin, header_key="EXPTIME", value_num=float(hdr0["EXPTIME"])))
            except Exception:
                pass
        db.session.add(FitsHeaderKeyvalue(fits_id=fits_bin, header_key="DATE-OBS", value_time=observed_at))

        db.session.flush()  # FK 확인

        # (선택) PREVIEW 1장 생성/저장
        # 2D/3D 대응: 3D면 중앙 프레임
        if arr.ndim == 3:
            arr2d = arr[arr.shape[0] // 2]
        else:
            arr2d = arr
        png_bytes, w, h, stats = to_png_bytes(arr2d, max_wh=1024, percent_clip=1.0)

        # 프리뷰 파일 저장 경로
        os.makedirs(PREVIEW_ROOT, exist_ok=True)
        out_name = f"{uuid.UUID(bytes=fits_bin).hex}_preview.png"
        out_path = os.path.join(PREVIEW_ROOT, out_name)
        with open(out_path, "wb") as f:
            f.write(png_bytes)

        # file_storage (png)
        img_file_bin = _uuid_bytes()
        img_storage = FileStorage(
            file_id=img_file_bin, file_path=out_path, media_type="image/png",
            file_size=os.path.getsize(out_path), sha256_hash=None
        )
        db.session.add(img_storage)

        # preview_image
        pv_bin = _uuid_bytes()
        preview = PreviewImage(
            preview_id=pv_bin, fits_id=fits_bin, hdu_id=hdu_bin, storage_file_id=img_file_bin,
            image_kind="PREVIEW", frame_index=None, channel_name=None,
            width_px=w, height_px=h, stats_json=stats
        )
        db.session.add(preview)

        db.session.commit()
        return uuid.UUID(bytes=fits_bin).hex, shape, hdr0
    except Exception:
        db.session.rollback()
        raise

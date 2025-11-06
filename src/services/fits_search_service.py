# src/services/fits_search_service.py
from __future__ import annotations
from typing import Optional, List, Dict, Any
from src.models import db, FitsFile, PreviewImage, FileStorage

def get_fits_metadata(fits_id_hex: str) -> Dict[str, Any]:
    fid = bytes.fromhex(fits_id_hex)
    row: FitsFile = db.session.get(FitsFile, fid)
    if not row:
        raise KeyError("fits not found")
    return {
        "fits_id": fits_id_hex,
        "filename": row.original_filename or row.canonical_name,
        "canonical": row.canonical_name,
        "observed_at": row.observed_at.isoformat(),
        "instrument_id": row.instrument_id,
        "status": row.status,
    }

def get_preview_path(fits_id_hex: str) -> str:
    fid = bytes.fromhex(fits_id_hex)
    q = (
        db.session.query(PreviewImage, FileStorage)
        .join(FileStorage, PreviewImage.storage_file_id == FileStorage.file_id)
        .filter(PreviewImage.fits_id == fid, PreviewImage.image_kind == "PREVIEW")
        .order_by(PreviewImage.created_at.asc())
        .limit(1)
    )
    row = q.first()
    if not row:
        raise FileNotFoundError("preview not found")
    _, storage = row
    return storage.file_path

def search_fits_files(keyword: Optional[str]=None, date_from=None, date_to=None, limit:int=50) -> List[Dict[str,Any]]:
    q = db.session.query(FitsFile)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter((FitsFile.canonical_name.like(like)) | (FitsFile.original_filename.like(like)))
    if date_from and date_to:
        q = q.filter(FitsFile.observed_at.between(date_from, date_to))
    q = q.order_by(FitsFile.observed_at.desc()).limit(limit)

    return [{
        "fits_id": f.fits_id.hex(),
        "filename": f.original_filename,
        "observed_at": f.observed_at.isoformat(),
        "status": f.status,
    } for f in q.all()]

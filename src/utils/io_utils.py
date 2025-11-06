# src/utils/io_utils.py
from __future__ import annotations
import os,hashlib
from datetime import datetime

def sha256_hex(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1<<20), b""):
            h.update(chunk)
    return h.hexdigest()

def parse_date_obs(header: dict) -> datetime:
    """
    FITS header에서 DATE-OBS/DATE 파싱 → datetime
    '...Z'는 잘라내고, 마이크로초 허용
    """
    s = header.get("DATE-OBS") or header.get("DATE")
    if not s:
        raise ValueError("DATE-OBS not found in header")
    s = str(s).rstrip("Z")
    return datetime.fromisoformat(s)

def standard_Filename(original_name: str, header: dict) -> str:
    """
    파일명/헤더 기반 표준명 규칙(네 서비스 규칙대로 바꿔도 됨).
    예: NXST_YYYY-MM-DDTHH-MM-SS(.mmmmmm) 형태
    """
    dt = parse_date_obs(header)
    stem = os.path.splitext(os.path.basename(original_name))[0]
    # 필요하면 INSTRUME/LEVEL 등도 조합
    return f"{stem.split('_')[0]}_{dt.strftime('%Y-%m-%dT%H-%M-%S')}"

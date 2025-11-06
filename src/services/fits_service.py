# src/services/fits_service.py
from .fits_import_service import register_fits_to_db
from .fits_search_service import get_fits_metadata, get_preview_path

def register_fits(path: str):
    return register_fits_to_db(path)

def load_preview_bytes(fits_id_hex: str) -> bytes:
    p = get_preview_path(fits_id_hex)
    with open(p, "rb") as f:
        return f.read()

# 예: 메타 조회 사용처
def get_meta_for_api(fits_id_hex: str):
    return get_fits_metadata(fits_id_hex)

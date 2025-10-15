# src/scripts/ingest_from_png.py
from __future__ import annotations
import argparse, os, re, hashlib
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

from PIL import Image
from astropy.io import fits

from ..App import create_app
from ..model import db
from ..model.models import (
    FileStorage, FitsFile, FitsHeaderKeyvalue, Instrument, FitsHDU,
    PreviewImage, gen_uuid_bytes, uuid_bytes_to_hex
)

# ---------- utils ----------
def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def parse_date_obs_from_header(hdr) -> Optional[datetime]:
    for k in ("DATE-OBS", "DATE_OBS", "DATE"):
        v = hdr.get(k)
        if not v:
            continue
        s = str(v).replace('Z','').replace('T',' ')
        try:
            return datetime.fromisoformat(s)
        except Exception:
            pass
    return None

def parse_dt_from_filename(date: str, time: str) -> Optional[datetime]:
    """date='YYYYMMDD', time='HHMMSS[.micro]' -> datetime (naive)"""
    try:
        yyyy, mm, dd = int(date[0:4]), int(date[4:6]), int(date[6:8])
        hh, mi, ss = int(time[0:2]), int(time[2:4]), int(time[4:6])
        micro = 0
        if '.' in time:
            frac = time.split('.', 1)[1]
            micro = int((frac + "000000")[:6])  # pad to 6
        return datetime(yyyy, mm, dd, hh, mi, ss, micro)
    except Exception:
        return None

def seconds_of_day(time: str) -> Optional[int]:
    """HHMMSS(.micro) -> 0..86399"""
    try:
        hh, mi, ss = int(time[0:2]), int(time[2:4]), int(time[4:6])
        return hh*3600 + mi*60 + ss
    except Exception:
        return None

def get_or_create_instrument(name: Optional[str]) -> Optional[int]:
    if not name:
        return None
    inst = db.session.query(Instrument).filter_by(name=name).first()
    if inst:
        return inst.instrument_id
    max_id = db.session.query(db.func.coalesce(db.func.max(Instrument.instrument_id), 0)).scalar()
    inst = Instrument(instrument_id=max_id + 1, name=name, observatory=None)
    db.session.add(inst)
    db.session.flush()
    return inst.instrument_id

def ensure_filestorage(path: Path, media: str) -> bytes:
    ex = db.session.query(FileStorage).filter_by(file_path=str(path.resolve())).first()
    if ex:
        return ex.file_id
    fs = FileStorage(
        file_id=gen_uuid_bytes(),
        file_path=str(path.resolve()),
        media_type=media,
        file_size=path.stat().st_size,
        sha256_hash=sha256_of(path),
    )
    db.session.add(fs); db.session.flush()
    return fs.file_id

# ---------- filename parsing ----------
PNG_PATTERN_DEFAULT = re.compile(
    r"^(?P<base>[a-z0-9]+)_(?P<date>\d{8})_(?P<time>\d{6}(?:\.\d{1,6})?)(?:_(?P<level>l\d+))?\.png$",
    re.IGNORECASE
)

def parse_png_filename(fname: str, pattern: re.Pattern = PNG_PATTERN_DEFAULT):
    """
    nxst_20241106_225310.658925_l1.png
    -> base='nxst', date='20241106', time='225310.658925', level='L1', frame_index=sec-of-day
    """
    m = pattern.match(fname)
    if not m:
        stem = fname.rsplit('.',1)[0].lower()
        return stem, None, None, None, None
    gd = m.groupdict()
    base  = (gd.get("base") or "").lower()
    date  = gd.get("date") or ""
    time  = gd.get("time") or ""
    level = (gd.get("level") or "").upper() if gd.get("level") else None
    fidx  = seconds_of_day(time)
    return base, date, time, level, fidx

# ---------- FITS resolve ----------
FITS_EXTS = (".fts", ".fit", ".fits", ".FTS", ".FIT", ".FITS")

def time_variants(t: str) -> set[str]:
    # '225310.658925' -> {'225310.658925','225310658925','225310_658925'}
    if not t:
        return set()
    return {t, t.replace('.', ''), t.replace('.', '_')}

def candidate_names(base: str, date: str, time: str, level: Optional[str]) -> list[str]:
    """
    만들어 볼 수 있는 가능한 FITS 스템들(확장자 제외).
    우선순위: level 포함 → level 미포함.
    """
    tv = list(time_variants(time)) if time else [""]
    names = []
    for tvt in tv:
        if level:
            names.append(f"{base}_{date}_{tvt}_{level.lower()}")
            names.append(f"{base}_{date}_{tvt}_{level.upper()}")
        names.append(f"{base}_{date}_{tvt}")
    # 중복 제거, 원래 순서 유지
    seen = set(); out = []
    for n in names:
        if n not in seen:
            seen.add(n); out.append(n)
    return out

def find_fits_in_root(fits_root: Path, base: str, date: str, time: str, level: Optional[str]) -> Optional[Path]:
    # 1) 직속 경로에서 후보 조합 빠르게 시도
    for stem in candidate_names(base, date, time, level):
        for ext in FITS_EXTS:
            p = fits_root / f"{stem}{ext}"
            if p.exists():
                return p

    # 2) 재귀 탐색 (느슨 매칭)
    cands = []
    for ext in ("*.fts","*.fit","*.fits","*.FTS","*.FIT","*.FITS"):
        cands.extend(list(fits_root.rglob(ext)))

    # 정규화 비교: 소문자, '.' '_' 제거
    def norm(s: str) -> str:
        return s.lower().replace('.', '').replace('_','')

    targets = [norm(stem) for stem in candidate_names(base, date, time, level)]
    for p in cands:
        if norm(p.stem) in targets:
            return p

    # 마지막: base+date만으로 가장 근접해 보이는 것 (주의: 모호할 수 있음)
    base_date = norm(f"{base}_{date}")
    for p in cands:
        if base_date in norm(p.stem):
            return p

    return None

# ---------- ingest ----------
def ingest_fits_if_needed(fits_path: Path, fallback_dt: Optional[datetime]) -> bytes:
    """FITS가 DB에 없으면 등록하고 fits_id 반환. 이미 있으면 재사용."""
    ex_fs = db.session.query(FileStorage).filter_by(file_path=str(fits_path.resolve())).first()
    if ex_fs:
        ex_ff = db.session.query(FitsFile).filter_by(storage_file_id=ex_fs.file_id).first()
        if ex_ff:
            return ex_ff.fits_id

    storage_file_id = ensure_filestorage(fits_path, "application/fits")

    with fits.open(fits_path, memmap=False, do_not_scale_image_data=True) as hdul:
        prim = hdul[0].header if len(hdul) else {}
        observed_at = parse_date_obs_from_header(prim) or fallback_dt or datetime.utcnow()
        instrument_id = get_or_create_instrument(prim.get("INSTRUME"))

        ff = FitsFile(
            fits_id=gen_uuid_bytes(),
            storage_file_id=storage_file_id,
            original_filename=fits_path.name,
            canonical_name=fits_path.name,
            observed_at=observed_at,
            instrument_id=instrument_id,
            status="READY",
        )
        db.session.add(ff); db.session.flush()

        # OBJECT / EXPTIME / FRAMES|NAXIS3
        obj = prim.get("OBJECT")
        if obj:
            db.session.add(FitsHeaderKeyvalue(
                keyvalue_id=None, fits_id=ff.fits_id,
                header_key="OBJECT", value_text=str(obj)
            ))
        exptime = prim.get("EXPTIME")
        if exptime is not None:
            try:
                db.session.add(FitsHeaderKeyvalue(
                    keyvalue_id=None, fits_id=ff.fits_id,
                    header_key="EXPTIME", value_num=float(exptime)
                ))
            except: pass
        frames = prim.get("FRAMES") or prim.get("NAXIS3")
        if frames is not None:
            try:
                db.session.add(FitsHeaderKeyvalue(
                    keyvalue_id=None, fits_id=ff.fits_id,
                    header_key="NAXIS3", value_num=float(frames)
                ))
            except: pass

        # HDU 요약
        from astropy.io.fits import PrimaryHDU, ImageHDU, TableHDU, BinTableHDU
        for idx, h in enumerate(hdul):
            h_type = "OTHER"
            if isinstance(h, (PrimaryHDU, ImageHDU)): h_type = "IMAGE"
            elif isinstance(h, (TableHDU, BinTableHDU)): h_type = "TABLE"
            shape = None
            if getattr(h, "data", None) is not None:
                try: shape = list(h.data.shape)
                except: shape = None
            hdr_json = {k: str(h.header.get(k)) for k in list(h.header.keys())[:128]}
            db.session.add(FitsHDU(
                hdu_id=gen_uuid_bytes(), fits_id=ff.fits_id,
                hdu_index=idx, hdu_type=h_type,
                bitpix=int(h.header.get("BITPIX") or 0) if h.header else None,
                shape_json=shape, header_json=hdr_json
            ))

    return ff.fits_id

def upsert_png_frame(fits_id: bytes, png_path: Path, level: Optional[str], frame_index: Optional[int]) -> Optional[bytes]:
    # FileStorage upsert
    storage_file_id = ensure_filestorage(png_path, "image/png")
    # 이미 PreviewImage(storage_file_id unique)이면 스킵
    ex = db.session.query(PreviewImage).filter_by(storage_file_id=storage_file_id).first()
    if ex:
        return ex.preview_id

    # 이미지 크기
    try:
        with Image.open(png_path) as im:
            w, h = im.size
    except Exception as e:
        print(f"[SKIP:open] {png_path} ({e})")
        return None

    pr = PreviewImage(
        preview_id=gen_uuid_bytes(),
        fits_id=fits_id,
        hdu_id=None,
        storage_file_id=storage_file_id,
        image_kind="FRAME",
        frame_index=frame_index,          # sec-of-day (0..86399)
        channel_name=(level or "TIME").upper(),
        width_px=w, height_px=h,
        stats_json=None,
    )
    db.session.add(pr); db.session.flush()
    return pr.preview_id

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser(description="Ingest PNG frames by locating original FITS (.fts/.fit/.fits)")
    ap.add_argument("--png-root", required=True, help="PNG frames root")
    ap.add_argument("--fits-root", required=True, help="Original FITS root")
    ap.add_argument("--pattern", default=PNG_PATTERN_DEFAULT.pattern,
                    help="Regex for PNG name: base/date/time/(level)")
    args = ap.parse_args()

    png_root = Path(args.png_root)
    fits_root = Path(args.fits_root)
    if not png_root.exists(): raise SystemExit(f"PNG root not found: {png_root}")
    if not fits_root.exists(): raise SystemExit(f"FITS root not found: {fits_root}")

    pat = re.compile(args.pattern, re.IGNORECASE)

    app = create_app()
    with app.app_context():
        total, linked, skipped = 0, 0, 0
        for png in png_root.rglob("*.png"):
            if not png.is_file(): continue
            total += 1

            base, date, time, level, fidx = parse_png_filename(png.name, pat)
            if not base or not date or not time:
                print(f"[SKIP:parse] {png.name}")
                skipped += 1
                continue

            fits_path = find_fits_in_root(fits_root, base, date, time, level)
            if not fits_path:
                print(f"[SKIP:fits-not-found] base={base} date={date} time={time} level={level} file={png.name}")
                skipped += 1
                continue

            fallback_dt = parse_dt_from_filename(date, time)

            try:
                fits_id = ingest_fits_if_needed(fits_path, fallback_dt=fallback_dt)
                pr_id = upsert_png_frame(fits_id, png, level=level, frame_index=fidx)
                db.session.commit()
                if pr_id:
                    print(f"[OK] PNG={png.name} -> FITS={fits_path.name} preview={uuid_bytes_to_hex(pr_id)}")
                    linked += 1
                else:
                    print(f"[SKIP:preview-exists] PNG={png.name}")
            except Exception as e:
                db.session.rollback()
                print(f"[ERROR] {png}: {e}")

        print(f"[DONE] total={total}, linked={linked}, skipped={skipped}")

if __name__ == "__main__":
    main()

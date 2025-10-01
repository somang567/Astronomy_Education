from __future__ import annotations
from flask import Blueprint, render_template, request, jsonify
from sqlalchemy import or_, asc, desc, func, and_
from sqlalchemy.orm import aliased

from ..model import db
from ..model.models import (
    FitsFile, Instrument, FitsHeaderKeyvalue,
    PreviewImage, Tag, FitsTagMap, uuid_bytes_to_hex
)

search_bp = Blueprint("search", __name__)

@search_bp.get("/search")
def search():
    """
    필터 UI용 Instrument 목록.
    현재 등록된 FitsFile에 연결된 Instrument.name을 distinct로 수집.
    """
    instruments = (
        db.session.query(Instrument.name)
        .join(FitsFile, Instrument.instrument_id == FitsFile.instrument_id)
        .filter(Instrument.name.isnot(None))
        .distinct()
        .order_by(Instrument.name.asc())
        .all()
    )
    instruments = [row[0] for row in instruments]
    return render_template("search/dataSearch.html", instruments=instruments)


@search_bp.get("/api/search")
def api_search():
    # --- Query params ---
    q            = (request.args.get("q") or "").strip()
    date_from    = request.args.get("date_from")   # "YYYY-MM-DD" or ISO
    date_to      = request.args.get("date_to")
    instruments  = request.args.get("instrument") or ""  # "INST1,INST2"
    flags        = request.args.get("flags") or ""       # 태그 이름 "raw,calib"
    exp_min      = request.args.get("exp_min", type=float)
    exp_max      = request.args.get("exp_max", type=float)
    fr_min       = request.args.get("frames_min", type=int)
    fr_max       = request.args.get("frames_max", type=int)
    sort         = request.args.get("sort") or "-observed_at"

    # Header key aliases
    KV_OBJECT = aliased(FitsHeaderKeyvalue)
    KV_EXPT   = aliased(FitsHeaderKeyvalue)
    KV_FRM    = aliased(FitsHeaderKeyvalue)  # FRAMES 또는 NAXIS3
    THUMB     = aliased(PreviewImage)

    # 베이스 쿼리
    qset = (
        db.session.query(
            FitsFile,
            Instrument.name.label("instrument_name"),
            KV_OBJECT.value_text.label("object_name"),
            KV_EXPT.value_num.label("exptime"),
            KV_FRM.value_num.label("frames"),
            THUMB.preview_id.label("thumb_id"),
        )
        .outerjoin(Instrument, Instrument.instrument_id == FitsFile.instrument_id)
        .outerjoin(KV_OBJECT, and_(
            KV_OBJECT.fits_id == FitsFile.fits_id,
            KV_OBJECT.header_key == "OBJECT",
        ))
        .outerjoin(KV_EXPT, and_(
            KV_EXPT.fits_id == FitsFile.fits_id,
            KV_EXPT.header_key == "EXPTIME",
        ))
        .outerjoin(KV_FRM, and_(
            KV_FRM.fits_id == FitsFile.fits_id,
            KV_FRM.header_key.in_(["FRAMES", "NAXIS3"]),
        ))
        .outerjoin(THUMB, and_(
            THUMB.fits_id == FitsFile.fits_id,
            THUMB.image_kind == "THUMB",
        ))
    )

    # 검색어: 파일명/표준명/OBJECT
    if q:
        like = f"%{q}%"
        qset = qset.filter(or_(
            FitsFile.original_filename.ilike(like),
            FitsFile.canonical_name.ilike(like),
            KV_OBJECT.value_text.ilike(like),
        ))

    # 날짜범위: observed_at 기준
    if date_from:
        qset = qset.filter(FitsFile.observed_at >= date_from)
    if date_to:
        qset = qset.filter(FitsFile.observed_at <= date_to)

    # 기기 필터: Instrument.name
    if instruments:
        vals = [v for v in instruments.split(",") if v]
        if vals:
            qset = qset.filter(Instrument.name.in_(vals))

    # 태그 필터: 모든 태그 포함(AND) 방식
    if flags:
        tag_names = [v for v in flags.split(",") if v]
        for tn in tag_names:
            sub = (
                db.session.query(FitsTagMap.fits_id)
                .join(Tag, Tag.tag_id == FitsTagMap.tag_id)
                .filter(and_(
                    FitsTagMap.fits_id == FitsFile.fits_id,
                    Tag.name == tn,
                ))
                .exists()
            )
            qset = qset.filter(sub)

    # 노출/프레임 수 범위
    if exp_min is not None:
        qset = qset.filter(KV_EXPT.value_num >= exp_min)
    if exp_max is not None:
        qset = qset.filter(KV_EXPT.value_num <= exp_max)
    if fr_min is not None:
        qset = qset.filter(KV_FRM.value_num >= fr_min)
    if fr_max is not None:
        qset = qset.filter(KV_FRM.value_num <= fr_max)

    # 정렬
    sort_map = {
        "observed_at":  asc(FitsFile.observed_at),
        "-observed_at": desc(FitsFile.observed_at),
        "filename":     asc(FitsFile.original_filename),
        "-filename":    desc(FitsFile.original_filename),
        "object":       asc(func.coalesce(KV_OBJECT.value_text, "")),
        "-object":      desc(func.coalesce(KV_OBJECT.value_text, "")),
        "exptime":      asc(func.coalesce(KV_EXPT.value_num, 0)),
        "-exptime":     desc(func.coalesce(KV_EXPT.value_num, 0)),
        "instrument":   asc(func.coalesce(Instrument.name, "")),
        "-instrument":  desc(func.coalesce(Instrument.name, "")),
    }
    qset = qset.order_by(sort_map.get(sort, desc(FitsFile.observed_at)))

    # 페이징(간단히 60개 제한)
    rows = qset.limit(60).all()

    # 총 개수(대강): distinct fits_id 기준
    total = (
        db.session.query(func.count(func.distinct(FitsFile.fits_id)))
        .select_from(FitsFile)
        .all()[0][0]
    )

    def thumb_url_from_preview_id(preview_id: bytes | None) -> str | None:
        if not preview_id:
            return None
        return f"/fits/preview/{uuid_bytes_to_hex(preview_id)}"

    # 응답: 프론트의 기존 키 유지 (date_obs/target 등은 맵핑)
    items = []
    for (f, instrument_name, object_name, exptime, frames, thumb_id) in rows:
        items.append({
            # 기존 프런트 호환: file_id → fits_id로 맵핑
            "file_id":   uuid_bytes_to_hex(f.fits_id),
            "filename":  f.original_filename or f.canonical_name,
            "target":    object_name,  # OBJECT 헤더
            "date_obs":  f.observed_at.isoformat() if f.observed_at else None,
            "exptime":   exptime,
            "frames":    int(frames) if frames is not None else None,
            "shape":     None,  # 필요시 FitsHDU.shape_json에서 만드세요
            "flags":     [],    # 필요시 Tag 조인으로 확장
            "instrument": instrument_name,
            "thumb_url":  thumb_url_from_preview_id(thumb_id),
        })

    return jsonify({"total": total, "items": items})

# src/controller/searchController.py
from __future__ import annotations
from flask import Blueprint, render_template, request, jsonify, url_for
from sqlalchemy import or_, asc, desc, func, and_
from sqlalchemy.orm import aliased

from ..model import db
from ..model.models import FitsFile, Instrument, FitsHeaderKeyvalue, PreviewImage

search_bp = Blueprint("search", __name__)

@search_bp.get("/search")
def search():
    instruments = [row[0] for row in (
        db.session.query(Instrument.name)
        .join(FitsFile, FitsFile.instrument_id == Instrument.instrument_id)
        .distinct()
        .order_by(Instrument.name.asc())
        .all()
    )]
    return render_template("search/dataSearch.html", instruments=instruments)

@search_bp.get("/api/search")
def api_search():
    q          = (request.args.get("q") or "").strip()
    date_from  = request.args.get("date_from")
    date_to    = request.args.get("date_to")
    instruments= request.args.get("instrument") or ""
    flags      = request.args.get("flags") or ""   # (옵션: 별도 구현시 사용)
    exp_min    = request.args.get("exp_min", type=float)
    exp_max    = request.args.get("exp_max", type=float)
    fr_min     = request.args.get("frames_min", type=int)
    fr_max     = request.args.get("frames_max", type=int)
    sort       = request.args.get("sort") or "-observed_at"

    KV_OBJECT = aliased(FitsHeaderKeyvalue)
    KV_EXPT   = aliased(FitsHeaderKeyvalue)
    KV_FRM    = aliased(FitsHeaderKeyvalue)
    THUMB     = aliased(PreviewImage)
    FRAME     = aliased(PreviewImage)

    # THUMB 없으면 첫 FRAME을 썸네일로
    frame_min = (
        db.session.query(
            PreviewImage.fits_id.label("fid"),
            func.min(PreviewImage.frame_index).label("min_idx")
        )
        .filter(PreviewImage.image_kind == "FRAME")
        .group_by(PreviewImage.fits_id)
        .subquery()
    )

    qset = (
        db.session.query(
            FitsFile,
            Instrument.name.label("instrument_name"),
            KV_OBJECT.value_text.label("object_name"),
            KV_EXPT.value_num.label("exptime"),
            KV_FRM.value_num.label("frames"),
            func.coalesce(THUMB.preview_id, FRAME.preview_id).label("preview_id"),
        )
        .outerjoin(Instrument, Instrument.instrument_id == FitsFile.instrument_id)
        .outerjoin(KV_OBJECT, and_(KV_OBJECT.fits_id == FitsFile.fits_id, KV_OBJECT.header_key == "OBJECT"))
        .outerjoin(KV_EXPT,   and_(KV_EXPT.fits_id   == FitsFile.fits_id, KV_EXPT.header_key   == "EXPTIME"))
        .outerjoin(KV_FRM,    and_(KV_FRM.fits_id    == FitsFile.fits_id, KV_FRM.header_key.in_(["NAXIS3","FRAMES"])))
        .outerjoin(THUMB, and_(THUMB.fits_id==FitsFile.fits_id, THUMB.image_kind=="THUMB"))
        .outerjoin(frame_min, frame_min.c.fid == FitsFile.fits_id)
        .outerjoin(FRAME, and_(FRAME.fits_id==FitsFile.fits_id,
                               FRAME.image_kind=="FRAME",
                               FRAME.frame_index==frame_min.c.min_idx))
    )

    if q:
        like = f"%{q}%"
        qset = qset.filter(or_(KV_OBJECT.value_text.ilike(like),
                               FitsFile.original_filename.ilike(like)))

    if date_from:
        qset = qset.filter(FitsFile.observed_at >= date_from)
    if date_to:
        qset = qset.filter(FitsFile.observed_at <= date_to)

    if instruments:
        vals = [v for v in instruments.split(",") if v]
        if vals:
            qset = qset.filter(Instrument.name.in_(vals))

    if exp_min is not None:
        qset = qset.filter(KV_EXPT.value_num >= exp_min)
    if exp_max is not None:
        qset = qset.filter(KV_EXPT.value_num <= exp_max)
    if fr_min is not None:
        qset = qset.filter(KV_FRM.value_num >= fr_min)
    if fr_max is not None:
        qset = qset.filter(KV_FRM.value_num <= fr_max)

    sort_map = {
        "observed_at": asc(FitsFile.observed_at),
        "-observed_at": desc(FitsFile.observed_at),
        "object": asc(KV_OBJECT.value_text),
        "-exptime": desc(KV_EXPT.value_num),
        "exptime": asc(KV_EXPT.value_num),
    }
    qset = qset.order_by(sort_map.get(sort, desc(FitsFile.observed_at)))

    total = qset.count()
    rows = qset.limit(60).all()

    from uuid import UUID
    def preview_url(pid_bytes):
        if not pid_bytes:
            return None
        return url_for("fits.preview", preview_id_hex=UUID(bytes=pid_bytes).hex)

    items = []
    for ff, inst_name, obj, exptime, frames, pid in rows:
        items.append({
            "file_id":  ff.fits_id_hex,  # 프론트는 이 값을 fid로 사용
            "filename": ff.filename,
            "target":   obj,
            "date_obs": ff.observed_at.isoformat() if ff.observed_at else None,
            "exptime":  exptime,
            "frames":   int(frames) if frames is not None else None,
            "shape":    None,  # 필요하면 HDU에서 shape_json 꺼내 렌더
            "flags":    [],    # 필요시 구현
            "instrument": inst_name,
            "thumb_url":  preview_url(pid),
        })

    return jsonify({"total": total, "items": items})

# src/controller/fitsController.py (또는 fits blueprint 파일)
from __future__ import annotations
import os, base64, uuid, traceback
from uuid import UUID  # ✅ 추가
from sqlalchemy import asc  # ✅ 추가
from flask import Blueprint, request, jsonify, current_app, abort , send_file
from werkzeug.utils import secure_filename
from src.services import fits_service
from ..model import db
from ..model.models import PreviewImage, FileStorage

fits_bp = Blueprint("fits", __name__)

ALLOWED_EXT = {".fits", ".fts", ".fit"}

def _b64(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")

def _uploads_dir() -> str:
    root = current_app.root_path
    updir = os.path.join(root, "..", "uploads")
    updir = os.path.abspath(updir)
    os.makedirs(updir, exist_ok=True)
    return updir

def _clear_uploads():
    upload_dir = _uploads_dir()
    for f in os.listdir(upload_dir):
        fp = os.path.join(upload_dir, f)
        try:
            os.remove(fp)
            print(f"[삭제됨] {fp}")
        except Exception as e:
            print(f"[삭제 실패] {fp}: {e}")

@fits_bp.route("/upload", methods=["POST"])
def upload():
    try:
        if "file" not in request.files:
            return jsonify({"error": "파일이 없습니다"}), 400
        f = request.files["file"]
        if not f or not f.filename:
            return jsonify({"error": "파일명이 비어있습니다"}), 400

        ext = os.path.splitext(f.filename)[1].lower()
        if ALLOWED_EXT and ext not in ALLOWED_EXT:
            return jsonify({"error": f"허용되지 않은 확장자({ext})"}), 400

        _clear_uploads()

        base = secure_filename(os.path.basename(f.filename)) or "upload.fits"
        unique = f"{uuid.uuid4().hex[:8]}_{base}"
        upload_dir = _uploads_dir()
        path = os.path.join(upload_dir, unique)
        f.save(path)

        file_id, shape, header = fits_service.register_fits(path)
        png, w, h = fits_service.load_preview(file_id, percent_clip=1.0, apply_correction=False)

        return jsonify({
            "file_id": file_id,
            "filename": base,
            "saved_as": unique,
            "shape": list(shape) if shape else None,
            "header": header,
            "preview_png": _b64(png),
            "width": w,
            "height": h,
        })
    except Exception as e:
        return jsonify({
            "error": f"업로드 실패: {type(e).__name__}: {e}",
            "trace": traceback.format_exc(limit=3),
        }), 500

@fits_bp.route("/preview", methods=["GET"], endpoint="preview")
def preview_by_file():
    file_id = request.args.get("file_id")
    z = request.args.get("z", type=int)
    percent_clip = request.args.get("percent_clip", default=1.0, type=float)
    apply_correction = request.args.get("apply_correction", default="true").lower() == "true"
    if not file_id:
        return jsonify({"error": "file_id가 필요합니다"}), 400
    try:
        png, w, h = fits_service.load_preview(
            file_id, z=z, percent_clip=percent_clip, apply_correction=apply_correction
        )
        # ✅ 메타 함께 내려주기 (mainViewer.js의 refreshPreview에서 사용)
        meta = fits_service.get_meta(file_id)
        return jsonify({
            "preview_png": _b64(png),
            "width": w,
            "height": h,
            "filename": os.path.basename(meta.get("path") or "") or meta.get("header", {}).get("FILENAME"),
            "header": meta.get("header") or {},
        })
    except Exception as e:
        return jsonify({"error": f"프리뷰 실패: {type(e).__name__}: {e}"}), 500

@fits_bp.get("/preview/<preview_id_hex>", endpoint="preview_image")
def preview_image(preview_id_hex: str):
    try:
        pid = uuid.UUID(hex=preview_id_hex).bytes
    except Exception:
        abort(404)
    pr = db.session.query(PreviewImage).filter_by(preview_id=pid).first()
    if not pr:
        abort(404)
    fs = db.session.query(FileStorage).filter_by(file_id=pr.storage_file_id).first()
    if not fs:
        abort(404)
    return send_file(fs.file_path, mimetype=fs.media_type or "image/png")

@fits_bp.get("/frames/<fits_id_hex>", endpoint="frames")
def frames(fits_id_hex: str):
    try:
        fid = UUID(hex=fits_id_hex).bytes
    except Exception:
        abort(404)

    rows = (
        db.session.query(PreviewImage)
        .filter(PreviewImage.fits_id==fid, PreviewImage.image_kind=="FRAME")
        .order_by(asc(PreviewImage.frame_index))  # ✅ asc import 추가
        .all()
    )

    def to_hex(b: bytes|None) -> str|None:
        return UUID(bytes=b).hex if b else None

    items = [{
        "preview_id": to_hex(r.preview_id),
        "frame_index": r.frame_index,
        "channel": r.channel_name,
        "width": r.width_px,
        "height": r.height_px,
        "url": url_for("fits.preview_image", preview_id_hex=to_hex(r.preview_id))
    } for r in rows]

    return jsonify({"count": len(items), "items": items})

@fits_bp.route("/slit", methods=["GET"])
def slit():
    file_id = request.args.get("file_id")
    x = request.args.get("x", type=int)
    percent_clip = request.args.get("percent_clip", default=1.0, type=float)
    apply_correction = request.args.get("apply_correction", default="true").lower() == "true"
    if not file_id or x is None:
        return jsonify({"error": "file_id, x 가 필요합니다"}), 400
    try:
        png, w, h = fits_service.get_slit_image(
            file_id, x, percent_clip=percent_clip, apply_correction=apply_correction
        )
        return jsonify({"slit_png": _b64(png), "width": w, "height": h})
    except Exception as e:
        return jsonify({"error": f"슬릿 생성 실패: {type(e).__name__}: {e}"}), 500

@fits_bp.route("/spectrum", methods=["GET"])
def spectrum():
    file_id = request.args.get("file_id")
    x = request.args.get("x", type=int)
    y = request.args.get("y", type=int)
    apply_correction = request.args.get("apply_correction", default="true").lower() == "true"
    if not file_id or x is None or y is None:
        return jsonify({"error": "file_id, x, y 가 필요합니다"}), 400
    try:
        lam, spec = fits_service.get_spectrum(file_id, x, y, apply_correction=apply_correction)
        return jsonify({
            "wavelength": lam.tolist(),
            "intensity": spec.tolist(),
            "x": x,
            "y": y,
        })
    except Exception as e:
        return jsonify({"error": f"스펙트럼 추출 실패: {type(e).__name__}: {e}"}), 500

from __future__ import annotations
import os, base64, uuid, traceback
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from src.services import fits_service

fits_bp = Blueprint("fits", __name__)

ALLOWED_EXT = {".fits", ".fts", ".fit"}

def _b64(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")

# 업로드 경로
def _uploads_dir() -> str:
    root = current_app.root_path
    updir = os.path.join(root, "..", "uploads")
    updir = os.path.abspath(updir)
    os.makedirs(updir, exist_ok=True)
    return updir

# 파일 업로드 후 다른 fits 파일을 새로 업로드 할 경우 기존 업로드 파일삭제
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

        # 🔥 이전 업로드 파일 정리
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

@fits_bp.route("/preview", methods=["GET"])
def preview():
    file_id = request.args.get("file_id")
    z = request.args.get("z", type=int)
    percent_clip = request.args.get("percent_clip", default=1.0, type=float)
    apply_correction = request.args.get("apply_correction", default="true").lower() == "true"
    if not file_id:
        return jsonify({"error": "file_id가 필요합니다"}), 400
    try:
        png, w, h = fits_service.load_preview(file_id, z=z, percent_clip=percent_clip, apply_correction=apply_correction)
        return jsonify({"preview_png": _b64(png), "width": w, "height": h})
    except Exception as e:
        return jsonify({"error": f"프리뷰 실패: {type(e).__name__}: {e}"}), 500

@fits_bp.route("/slit", methods=["GET"])
def slit():
    file_id = request.args.get("file_id")
    x = request.args.get("x", type=int)
    percent_clip = request.args.get("percent_clip", default=1.0, type=float)
    apply_correction = request.args.get("apply_correction", default="true").lower() == "true"
    if not file_id or x is None:
        return jsonify({"error": "file_id, x 가 필요합니다"}), 400
    try:
        png, w, h = fits_service.get_slit_image(file_id, x, percent_clip=percent_clip, apply_correction=apply_correction)
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

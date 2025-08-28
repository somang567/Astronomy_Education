# app/controller/fits_controller.py
import os
from flask import Blueprint, request , jsonify
from src.services.fits_service import read_fits


fits_bp = Blueprint("fits", __name__)
UPLOAD_FOLDER = "uploads"
CACHE = {}

# [ 직접 샘플 긁어오는 용도 ]
# @fits_bp.route("/fits")
# def get_fits_data():
#     # List of FITS file paths to process.
#     # IMPORTANT: Ensure these paths are correct on your local machine.
#     file_paths = [
#         "/Users/juntk/Desktop/Astronomical Research Institute Data/Data/internship_challan_app/nxst_20241106_225310.658925_l1.fts",
#         "/Users/juntk/Desktop/Astronomical Research Institute Data/Data/internship_challan_app/nxst_20241106_225543.130151_l1.fts",
#         "/Users/juntk/Desktop/Astronomical Research Institute Data/Data/internship_challan_app/nxst_20241106_225815.343815_l1.fts",
#         "/Users/juntk/Desktop/Astronomical Research Institute Data/Data/internship_challan_app/nxst_20250810_212509.482436.fits",
#         "/Users/juntk/Desktop/Astronomical Research Institute Data/Data/internship_challan_app/nxst_20250810_212745.502083.fits",
#         "/Users/juntk/Desktop/Astronomical Research Institute Data/Data/internship_challan_app/nxst_20250810_213021.521724.fits",
#     ]
    
#     results = []
    
#     for file_path in file_paths:
#         try:
#             # Check if the file exists before attempting to open it.
#             if not os.path.exists(file_path):
#                 results.append({
#                     "file_path": file_path,
#                     "error": "File not found."
#                 })
#                 continue
            
#             # Read FITS data and header.
#             data, header = read_fits(file_path)
            
#             results.append({
#                 "file_path": file_path,
#                 "shape": data.shape if data is not None else None,
#                 "header": dict(header)
#             })
            
#         except Exception as e:
#             # Catch all exceptions and report the error message.
#             results.append({
#                 "file_path": file_path,
#                 "error": f"Failed to process file: {str(e)}"
#             })
            
#     return jsonify(results)

@fits_bp.route("/upload", methods=["POST"])
def upload_fits():
    if "file" not in request.files: return jsonify({"error":"파일 없음"}), 400
    f = request.files["file"]
    if not f.filename: return jsonify({"error":"파일명 없음"}), 400
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    path = os.path.join(UPLOAD_DIR, f.filename)
    f.save(path)

    file_id, preview_png_b64, meta = load_fits_preview(path)   # ndarray 캐시 + PNG base64 생성
    CACHE[file_id] = meta  # 필요 시 ndarray는 services 내부 전역 캐시에 둬도 OK (메모리 관리 포함)

    return jsonify({
        "file_id": file_id,
        "filename": f.filename,
        "preview_png": preview_png_b64,  # "data:image/png;base64,...."
        "width": meta["width"], "height": meta["height"],
        "header": meta["header"]
    })

    


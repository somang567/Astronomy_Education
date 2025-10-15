# app/app.py
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from .mock.local_mock import mock_bp

# 1) .env 먼저 로드
ENV_FILE = find_dotenv(filename=".env", usecwd=True) or str(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(ENV_FILE, override=True)

print("[ENV] CHALLAN_APP_DIR =", os.getenv("CHALLAN_APP_DIR"))
print("[ENV] CHAILLAN_APP_DIR =", os.getenv("CHAILLAN_APP_DIR"))  # ← 이 키는 오타일 가능성 있음

# 2) 이후 Flask/DB import
from flask import Flask, render_template
from flask_migrate import Migrate  # type: ignore

# 블루프린트/DB/모델 상대임포트 (app 패키지 기준)
from .controller.FitsController import fits_bp
from .controller.searchController import search_bp
from .model import db

migrate = Migrate()  # ← 오타 수정 (migrAge -> migrAte)

def create_app():
    base_dir = Path(__file__).resolve().parent
    templates_path = base_dir.parent / "resources" / "templates"
    static_path = base_dir.parent / "resources" / "static"

    app = Flask(
        __name__,
        template_folder=str(templates_path),
        static_folder=str(static_path),
    )

    # DB 설정 (환경변수에서 읽거나 기본값)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "SQLALCHEMY_DATABASE_URI",
        "mysql+pymysql://user:pass@127.0.0.1:3306/yourdb?charset=utf8mb4",
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # DB/Migrate 초기화
    db.init_app(app)
    migrate.init_app(app, db)

    # 라우트
    @app.route("/")
    def main():
        return render_template("home/main.html")

    # 블루프린트 등록
    app.register_blueprint(fits_bp, url_prefix="/fits")
    app.register_blueprint(search_bp)  # /search, /api/search
    app.register_blueprint(mock_bp) # local_fits 파일과 테스트 하기 위함으로 만듦.
    return app

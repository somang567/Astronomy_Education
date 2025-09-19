# app.py
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

# 1) .env를 "가장 먼저" 로드 (작업 디렉터리/프로젝트 루트 모두 탐색)
ENV_FILE = find_dotenv(filename=".env", usecwd=True) or str(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(ENV_FILE, override=True)

# 2) 이제 읽으면 값이 나옵니다
print("[ENV] CHALLAN_APP_DIR =", os.getenv("CHALLAN_APP_DIR"))
print("[ENV] CHAILLAN_APP_DIR =", os.getenv("CHAILLAN_APP_DIR"))

# 3) env에 의존할 수 있는 것들은 "그 다음"에 import
from flask import Flask, render_template
from .controller.FitsController import fits_bp

def create_app():
    base_dir = Path(__file__).resolve().parent
    templates_path = base_dir.parent / "resources" / "templates"
    static_path = base_dir.parent / "resources" / "static"

    app = Flask(
        __name__,
        template_folder=str(templates_path),
        static_folder=str(static_path),
    )

    @app.route("/")
    def mainPage():
        return render_template("home/main.html")

    app.register_blueprint(fits_bp, url_prefix="/fits")
    return app

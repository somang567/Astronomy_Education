# src/app.py
from flask import Flask
from .controller.test import test_blueprint

def create_app():
    # Flask 애플리케이션 객체 생성
    app = Flask(__name__)
    
    # BLUEPRINT 등록
    app.register_blueprint(test_blueprint, url_prefix="/api")
    
    return app
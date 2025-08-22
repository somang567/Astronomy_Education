from flask import Flask
from .controller.test import test_blueprint

def create_app():
    app = Flask(__name__)
    
    # BLUEPRINT 등록
    app.register_blueprint(test_blueprint , url_prefix="/api")
    return app
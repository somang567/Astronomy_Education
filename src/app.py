import os
from flask import Flask, render_template
from .controller.FitsController import fits_bp

def create_app():
    # 현재 파일 기준 절대 경로
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # resources 폴더 기준 static / templates 경로
    templates_path = os.path.join(base_dir, '..', 'resources', 'templates')
    static_path = os.path.join(base_dir, '..', 'resources', 'static')

    app = Flask(
        __name__,
        template_folder=templates_path,
        static_folder=static_path
    )

    @app.route("/")
    def mainPage():
        return render_template("home/main.html")

    app.register_blueprint(fits_bp , url_prefix="/fits")
    return app

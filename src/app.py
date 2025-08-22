from flask import Flask , render_template
from .controller.TestController import test_blueprint

def create_app():
    # Flask 애플리케이션 객체 생성
    app = Flask(__name__ , 
                template_folder='../resources/templates')
    
    @app.route("/")
    def mainPage():
        return render_template("index.html")
    
    # BLUEPRINT 등록
    app.register_blueprint(test_blueprint, url_prefix="/api")
    
    return app

    

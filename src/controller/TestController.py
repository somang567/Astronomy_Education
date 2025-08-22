from flask import Blueprint , render_template

test_blueprint = Blueprint("test" , __name__)


@test_blueprint.route("/ping")
def ping():
    return {"msg" : "pong"}

@test_blueprint.route("/bath")
def bat():
    return render_template("index2.html")



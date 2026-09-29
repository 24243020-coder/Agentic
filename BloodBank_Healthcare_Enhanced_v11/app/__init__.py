from flask import Flask
from .db import init_db
from .rag import init_knowledge_base
from .agent import build_agent

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "bloodlink-demo-secret"
    init_db()
    init_knowledge_base()
    app.extensions["blood_agent"] = build_agent()
    from .routes import bp
    app.register_blueprint(bp)
    return app

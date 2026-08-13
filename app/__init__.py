import os
import uuid

from flask import Flask, g, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

db = SQLAlchemy()


def users_from_env():
    return [
        {
            "email": os.environ.get("BUDGET_USER1_EMAIL", "user1@example.com").lower(),
            "name": os.environ.get("BUDGET_USER1_NAME", "Лёня"),
            "dative": os.environ.get("BUDGET_USER1_NAME_DAT", "Лёне"),
            "side": "left",
        },
        {
            "email": os.environ.get("BUDGET_USER2_EMAIL", "user2@example.com").lower(),
            "name": os.environ.get("BUDGET_USER2_NAME", "Аня"),
            "dative": os.environ.get("BUDGET_USER2_NAME_DAT", "Ане"),
            "side": "right",
        },
    ]


def create_app(config=None):
    app = Flask(__name__)
    os.makedirs(app.instance_path, exist_ok=True)
    db_path = os.environ.get("DATABASE_PATH", os.path.join(app.instance_path, "budget.db"))
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path
    app.config["SPLIT_RATIO"] = os.environ.get("SPLIT_RATIO", "0.5")
    app.config["IDENTITY_HEADER"] = os.environ.get("IDENTITY_HEADER", "X-Forwarded-Email")
    app.config["MOCK_AUTH_EMAIL"] = os.environ.get("MOCK_AUTH_EMAIL", "")
    app.config["USERS"] = users_from_env()
    if config:
        app.config.update(config)

    db.init_app(app)

    from . import models  # noqa: F401  (register models before create_all)
    from . import services
    from .routes import bp

    with app.app_context():
        db.create_all()
        _migrate()
        _seed(app)

    app.register_blueprint(bp)

    app.jinja_env.filters["money"] = services.fmt_money
    app.jinja_env.filters["when"] = services.fmt_when

    @app.before_request
    def identify():
        from .models import User

        header = app.config["IDENTITY_HEADER"]
        email = (request.headers.get(header) or app.config["MOCK_AUTH_EMAIL"] or "").strip().lower()
        g.user = None
        g.set_device_cookie = None
        if email:
            g.user = User.query.filter(func.lower(User.email) == email).first()
            g.actor = email
            g.actor_display = g.user.display_name if g.user else "Гость"
        else:
            device_id = request.cookies.get("device_id")
            if not device_id:
                device_id = uuid.uuid4().hex
                g.set_device_cookie = device_id
            ua = request.user_agent.string or ""
            platform = next(
                (label for probe, label in [
                    ("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"),
                    ("Macintosh", "Mac"), ("Windows", "Win"), ("Linux", "Linux"),
                ] if probe in ua),
                "Устройство",
            )
            g.actor = f"{platform}-{device_id[:4]} · без входа"
            g.actor_display = g.actor

    @app.after_request
    def set_device_cookie(response):
        if getattr(g, "set_device_cookie", None):
            response.set_cookie(
                "device_id", g.set_device_cookie,
                max_age=60 * 60 * 24 * 730, httponly=True, samesite="Lax",
            )
        return response

    return app


def _migrate():
    """create_all() never alters existing tables — add columns introduced
    after the first release to already-created databases."""
    from sqlalchemy import text

    existing = {row[1] for row in db.session.execute(text("PRAGMA table_info(users)"))}
    for column, ddl in [
        ("last_year", "ALTER TABLE users ADD COLUMN last_year INTEGER"),
        ("last_month", "ALTER TABLE users ADD COLUMN last_month INTEGER"),
    ]:
        if column not in existing:
            db.session.execute(text(ddl))
    db.session.commit()


def _seed(app):
    from .models import Group, Tag, User

    for cfg in app.config["USERS"]:
        user = User.query.filter_by(side=cfg["side"]).first()
        if user is None:
            db.session.add(User(
                email=cfg["email"], display_name=cfg["name"],
                name_dative=cfg["dative"], side=cfg["side"],
            ))
        else:
            user.email = cfg["email"]
            user.display_name = cfg["name"]
            user.name_dative = cfg["dative"]

    if Group.query.count() == 0:
        for i, name in enumerate(["Счета", "Рассрочки", "Траты", "Долги", "Отложить"]):
            db.session.add(Group(name=name, sort_order=i))

    if Tag.query.count() == 0:
        for i, name in enumerate(["SWED", "COOP", "SEB 2", "BIGBANK"]):
            db.session.add(Tag(name=name, sort_order=i))

    db.session.commit()

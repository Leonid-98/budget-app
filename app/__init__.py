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
    app.jinja_env.globals["STATUSES"] = services.STATUSES
    app.jinja_env.globals["STATUS_LABEL"] = services.STATUS_LABEL
    app.jinja_env.globals["STATUS_CLASS"] = services.STATUS_CLASS

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
    """create_all() never alters existing tables — evolve databases created
    by earlier releases."""
    from sqlalchemy import text

    users_cols = {row[1] for row in db.session.execute(text("PRAGMA table_info(users)"))}
    for column, ddl in [
        ("last_year", "ALTER TABLE users ADD COLUMN last_year INTEGER"),
        ("last_month", "ALTER TABLE users ADD COLUMN last_month INTEGER"),
    ]:
        if column not in users_cols:
            db.session.execute(text(ddl))

    # Tags were replaced by bank states: entries whose tag named a bank take
    # that bank as their status, then the tag machinery is dropped.
    entry_cols = {row[1] for row in db.session.execute(text("PRAGMA table_info(entries)"))}
    if "tag_id" in entry_cols:
        tagged = db.session.execute(text(
            "SELECT e.id, upper(t.name) FROM entries e JOIN tags t ON t.id = e.tag_id"
        )).all()
        bank_by_tag = {"SWED": "swed", "COOP": "coop", "BIGBANK": "big"}
        for entry_id, tag_name in tagged:
            state = bank_by_tag.get(tag_name, "seb" if tag_name.startswith("SEB") else None)
            if state:
                db.session.execute(
                    text("UPDATE entries SET status = :state WHERE id = :id"),
                    {"state": state, "id": entry_id},
                )
        # tag_id sits inside a FOREIGN KEY clause of the original table, so
        # SQLite refuses DROP COLUMN — rebuild the table from the current model.
        db.session.execute(text("ALTER TABLE entries RENAME TO entries_old"))
        db.session.commit()
        db.create_all()  # recreates `entries` from the model, without tag_id
        db.session.execute(text(
            "INSERT INTO entries (id, month_id, user_id, group_id, name, amount_cents,"
            " status, sort_order, created_at, updated_at)"
            " SELECT id, month_id, user_id, group_id, name, amount_cents,"
            " status, sort_order, created_at, updated_at FROM entries_old"))
        db.session.execute(text("DROP TABLE entries_old"))
        db.session.execute(text("DROP TABLE IF EXISTS tags"))

    db.session.commit()


def _seed(app):
    from .models import Group, User

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

    db.session.commit()

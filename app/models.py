from datetime import datetime

from . import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String, unique=True, nullable=False)
    display_name = db.Column(db.String, nullable=False)
    name_dative = db.Column(db.String, nullable=False)
    side = db.Column(db.String, unique=True, nullable=False)  # left | right
    accent_color = db.Column(db.String, nullable=False, default="teal")
    theme = db.Column(db.String, nullable=False, default="system")


class Month(db.Model):
    __tablename__ = "months"
    __table_args__ = (db.UniqueConstraint("year", "month"),)

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)


class MonthIncome(db.Model):
    __tablename__ = "month_incomes"

    month_id = db.Column(db.Integer, db.ForeignKey("months.id"), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    amount_cents = db.Column(db.Integer, nullable=False, default=0)


class Group(db.Model):
    __tablename__ = "groups"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True, nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    archived = db.Column(db.Boolean, nullable=False, default=False)


class Tag(db.Model):
    __tablename__ = "tags"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True, nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)


class Entry(db.Model):
    __tablename__ = "entries"

    id = db.Column(db.Integer, primary_key=True)
    month_id = db.Column(db.Integer, db.ForeignKey("months.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    name = db.Column(db.String, nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String, nullable=False, default="pending")  # paid | pending
    tag_id = db.Column(db.Integer, db.ForeignKey("tags.id"), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    month = db.relationship("Month")
    user = db.relationship("User")
    group = db.relationship("Group")
    tag = db.relationship("Tag")


class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    actor = db.Column(db.String, nullable=False)  # email or device label, never rendered as email
    message = db.Column(db.String, nullable=False)
    month_label = db.Column(db.String, nullable=True)

from datetime import date

from flask import Blueprint, abort, current_app, g, redirect, render_template, request, url_for

from . import db
from .models import Entry, Group, Month, MonthIncome, Tag, User
from . import services

bp = Blueprint("main", __name__)


def _month_url(year, month, **params):
    return url_for("main.month_view", year=year, month=month, **params)


def _back(month_row, **params):
    return redirect(_month_url(month_row.year, month_row.month, **params))


@bp.get("/")
def index():
    if g.user and g.user.last_year and g.user.last_month:
        return redirect(_month_url(g.user.last_year, g.user.last_month))
    today = date.today()
    return redirect(_month_url(today.year, today.month))


@bp.get("/m/<int:year>/<int:month>")
def month_view(year, month):
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        abort(404)
    m = services.ensure_month(year, month)

    if g.user and (g.user.last_year, g.user.last_month) != (year, month):
        g.user.last_year, g.user.last_month = year, month
        db.session.commit()

    users = User.query.order_by(User.side).all()  # left, right
    left = next(u for u in users if u.side == "left")
    right = next(u for u in users if u.side == "right")
    groups = Group.query.filter_by(archived=False).order_by(Group.sort_order, Group.id).all()
    tags = Tag.query.order_by(Tag.sort_order, Tag.id).all()

    entries = (Entry.query.filter_by(month_id=m.id)
               .order_by(Entry.sort_order, Entry.id).all())
    incomes = {i.user_id: i.amount_cents for i in MonthIncome.query.filter_by(month_id=m.id)}

    sides = []
    for user in (left, right):
        user_entries = [e for e in entries if e.user_id == user.id]
        grouped = [(grp, [e for e in user_entries if e.group_id == grp.id]) for grp in groups]
        grouped = [(grp, items) for grp, items in grouped if items]
        expenses = sum(e.amount_cents for e in user_entries)
        sides.append({
            "user": user,
            "income": incomes.get(user.id, 0),
            "grouped": grouped,
            "expenses": expenses,
            "free": incomes.get(user.id, 0) - expenses,
        })

    _, _, transfer = services.settlement(
        sides[0]["income"], sides[0]["expenses"],
        sides[1]["income"], sides[1]["expenses"],
        current_app.config["SPLIT_RATIO"],
    )
    if transfer > 0:
        transfer_ctx = {"sender": left, "receiver": right, "amount": transfer}
    elif transfer < 0:
        transfer_ctx = {"sender": right, "receiver": left, "amount": -transfer}
    else:
        transfer_ctx = None

    prev_y, prev_m = services.prev_ym(year, month)
    next_y, next_m = services.next_ym(year, month)
    prev_month_row = Month.query.filter_by(year=prev_y, month=prev_m).first()
    prev_has_entries = bool(
        prev_month_row and Entry.query.filter_by(month_id=prev_month_row.id).count()
    )

    edit_id = request.args.get("edit", type=int)

    return render_template(
        "month.html",
        m=m,
        label=services.month_label(year, month),
        prev={"url": _month_url(prev_y, prev_m), "name": services.MONTHS_NOM[prev_m - 1]},
        next={"url": _month_url(next_y, next_m), "name": services.MONTHS_NOM[next_m - 1]},
        sides=sides,
        transfer=transfer_ctx,
        can_copy=(not entries and prev_has_entries),
        groups=groups,
        tags=tags,
        users=(left, right),
        audit=services.recent_audit(),
        actors={u.email: u.display_name for u in users},
        edit_id=edit_id,
        dlg=request.args.get("dlg", ""),
    )


@bp.post("/m/<int:year>/<int:month>/copy-prev")
def copy_prev(year, month):
    m = services.ensure_month(year, month)
    if Entry.query.filter_by(month_id=m.id).count():
        return _back(m)
    prev_y, prev_m = services.prev_ym(year, month)
    source = Month.query.filter_by(year=prev_y, month=prev_m).first()
    if source:
        services.copy_month(m, source, g.actor)
    return _back(m)


# ---------- entries ----------

def _entry_summary(entry):
    parts = [entry.group.name, services.fmt_money(entry.amount_cents)]
    if entry.tag:
        parts.append(entry.tag.name)
    return ", ".join(parts)


@bp.post("/entries")
def entry_create():
    m = db.get_or_404(Month, request.form.get("month_id", type=int) or 0)
    try:
        amount = services.parse_amount(request.form.get("amount", ""))
    except ValueError:
        return _back(m)
    name = (request.form.get("name") or "").strip()
    user = db.session.get(User, request.form.get("user_id", type=int) or 0)
    group = db.session.get(Group, request.form.get("group_id", type=int) or 0)
    if not name or user is None or group is None:
        return _back(m)
    tag = db.session.get(Tag, request.form.get("tag_id", type=int) or 0)

    last = (Entry.query
            .filter_by(month_id=m.id, user_id=user.id, group_id=group.id)
            .order_by(Entry.sort_order.desc()).first())
    entry = Entry(
        month_id=m.id, user_id=user.id, group_id=group.id, name=name,
        amount_cents=amount, tag_id=tag.id if tag else None,
        sort_order=(last.sort_order + 1) if last else 0,
    )
    db.session.add(entry)
    db.session.flush()
    services.log(g.actor, f"добавлено «{entry.name}» ({_entry_summary(entry)})",
                 services.month_label(m.year, m.month))
    db.session.commit()
    return _back(m)


@bp.post("/entries/<int:entry_id>/update")
def entry_update(entry_id):
    entry = db.get_or_404(Entry, entry_id)
    m = entry.month
    try:
        amount = services.parse_amount(request.form.get("amount", ""))
    except ValueError:
        return _back(m)
    name = (request.form.get("name") or "").strip()
    group = db.session.get(Group, request.form.get("group_id", type=int) or 0)
    if not name or group is None:
        return _back(m)
    tag = db.session.get(Tag, request.form.get("tag_id", type=int) or 0)
    tag_id = tag.id if tag else None

    changes = []
    if name != entry.name:
        changes.append(f"название «{entry.name}» → «{name}»")
    if amount != entry.amount_cents:
        changes.append(f"сумма {services.fmt_money(entry.amount_cents)} → {services.fmt_money(amount)}")
    if group.id != entry.group_id:
        changes.append(f"группа {entry.group.name} → {group.name}")
    if tag_id != entry.tag_id:
        old = entry.tag.name if entry.tag else "—"
        new = tag.name if tag else "—"
        changes.append(f"тег {old} → {new}")

    if changes:
        label = entry.name
        entry.name, entry.amount_cents, entry.group_id, entry.tag_id = name, amount, group.id, tag_id
        services.log(g.actor, f"«{label}»: " + ", ".join(changes),
                     services.month_label(m.year, m.month))
        db.session.commit()
    return _back(m)


@bp.post("/entries/<int:entry_id>/toggle")
def entry_toggle(entry_id):
    entry = db.get_or_404(Entry, entry_id)
    m = entry.month
    entry.status = "pending" if entry.status == "paid" else "paid"
    state = "оплачено" if entry.status == "paid" else "ожидает"
    services.log(g.actor, f"«{entry.name}» отмечено как {state}",
                 services.month_label(m.year, m.month))
    db.session.commit()
    return _back(m)


@bp.post("/entries/<int:entry_id>/delete")
def entry_delete(entry_id):
    entry = db.get_or_404(Entry, entry_id)
    m = entry.month
    services.log(g.actor, f"удалено «{entry.name}» ({_entry_summary(entry)})",
                 services.month_label(m.year, m.month))
    db.session.delete(entry)
    db.session.commit()
    return _back(m)


# ---------- settings (shared data) ----------

@bp.post("/settings/income/<int:user_id>")
def income_update(user_id):
    m = db.get_or_404(Month, request.form.get("month_id", type=int) or 0)
    user = db.get_or_404(User, user_id)
    try:
        amount = services.parse_amount(request.form.get("amount", ""))
    except ValueError:
        return _back(m, dlg="settings")

    current = MonthIncome.query.filter_by(month_id=m.id, user_id=user.id).first()
    old = current.amount_cents if current else 0
    if amount != old:
        key = m.year * 100 + m.month
        affected = (MonthIncome.query
                    .join(Month, MonthIncome.month_id == Month.id)
                    .filter(MonthIncome.user_id == user.id)
                    .filter((Month.year * 100 + Month.month) >= key)
                    .all())
        for row in affected:
            row.amount_cents = amount
        services.log(
            g.actor,
            f"Доход {user.display_name} {services.fmt_money(old)} → {services.fmt_money(amount)} (Настройки)",
        )
        db.session.commit()
    return _back(m, dlg="settings")


@bp.post("/settings/groups/add")
def group_add():
    m = db.get_or_404(Month, request.form.get("month_id", type=int) or 0)
    name = (request.form.get("name") or "").strip()
    if name and not Group.query.filter_by(name=name).first():
        last = Group.query.order_by(Group.sort_order.desc()).first()
        db.session.add(Group(name=name, sort_order=(last.sort_order + 1) if last else 0))
        services.log(g.actor, f"добавлена группа «{name}» (Настройки)")
        db.session.commit()
    return _back(m, dlg="settings")


@bp.post("/settings/groups/<int:group_id>/rename")
def group_rename(group_id):
    m = db.get_or_404(Month, request.form.get("month_id", type=int) or 0)
    group = db.get_or_404(Group, group_id)
    name = (request.form.get("name") or "").strip()
    if name and name != group.name and not Group.query.filter_by(name=name).first():
        services.log(g.actor, f"группа «{group.name}» → «{name}» (Настройки)")
        group.name = name
        db.session.commit()
    return _back(m, dlg="settings")


@bp.post("/settings/groups/<int:group_id>/move")
def group_move(group_id):
    m = db.get_or_404(Month, request.form.get("month_id", type=int) or 0)
    direction = request.form.get("dir")
    groups = Group.query.filter_by(archived=False).order_by(Group.sort_order, Group.id).all()
    idx = next((i for i, grp in enumerate(groups) if grp.id == group_id), None)
    if idx is not None:
        other = idx - 1 if direction == "up" else idx + 1
        if 0 <= other < len(groups):
            groups[idx].sort_order, groups[other].sort_order = (
                groups[other].sort_order, groups[idx].sort_order)
            db.session.commit()
    return _back(m, dlg="settings")


@bp.post("/settings/tags/add")
def tag_add():
    m = db.get_or_404(Month, request.form.get("month_id", type=int) or 0)
    name = (request.form.get("name") or "").strip()
    if name and not Tag.query.filter_by(name=name).first():
        last = Tag.query.order_by(Tag.sort_order.desc()).first()
        db.session.add(Tag(name=name, sort_order=(last.sort_order + 1) if last else 0))
        services.log(g.actor, f"добавлен тег «{name}» (Настройки)")
        db.session.commit()
    return _back(m, dlg="settings")


# ---------- personal preferences ----------

@bp.post("/prefs")
def prefs():
    if g.user is None:
        return ("", 204)
    accent = request.form.get("accent")
    theme = request.form.get("theme")
    if accent in {"teal", "violet", "ocean", "coral", "graphite", "rose"}:
        g.user.accent_color = accent
    if theme in {"system", "light", "dark"}:
        g.user.theme = theme
    db.session.commit()
    return ("", 204)

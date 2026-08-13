from app import db
from app.models import AuditLog, Entry, Group, Month, MonthIncome, User


def _month_id(app, year, month):
    with app.app_context():
        return Month.query.filter_by(year=year, month=month).first().id


def _add_entry(client, app, month_id, name="Квартира", amount="500,00", side="left"):
    with app.app_context():
        user = User.query.filter_by(side=side).first()
        group = Group.query.order_by(Group.sort_order).first()
        user_id, group_id = user.id, group.id
    return client.post("/entries", data={
        "month_id": month_id, "user_id": user_id, "group_id": group_id,
        "name": name, "amount": amount,
    })


def test_index_redirects_to_current_month(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/m/" in response.headers["Location"]


def test_index_opens_last_viewed_month(as_lenya, client, app):
    as_lenya.get("/m/2026/9")
    location = as_lenya.get("/").headers["Location"]
    assert location.endswith("/m/2026/9")

    as_lenya.get("/m/2026/8")
    location = as_lenya.get("/").headers["Location"]
    assert location.endswith("/m/2026/8")

    with app.app_context():
        anya = User.query.filter_by(side="right").first()
        assert anya.last_year is None  # per-user, other user unaffected

    from datetime import date
    today = date.today()
    location = client.get("/").headers["Location"]  # guest: current month
    assert location.endswith(f"/m/{today.year}/{today.month}")


def test_migration_adds_last_month_columns(app, tmp_path):
    from sqlalchemy import text
    from app import create_app

    with app.app_context():
        # simulate a pre-feature database
        db.session.execute(text("ALTER TABLE users DROP COLUMN last_year"))
        db.session.execute(text("ALTER TABLE users DROP COLUMN last_month"))
        db.session.commit()

    reopened = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": app.config["SQLALCHEMY_DATABASE_URI"],
        "USERS": app.config["USERS"],
    })
    with reopened.app_context():
        columns = {row[1] for row in db.session.execute(text("PRAGMA table_info(users)"))}
    assert {"last_year", "last_month"} <= columns


def test_month_page_renders(as_lenya, app):
    response = as_lenya.get("/m/2026/8")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Август 2026" in html
    assert "Лёня" in html and "Аня" in html
    assert "lenya@example.com" not in html  # emails never rendered


def test_entry_create_edit_toggle_delete(as_lenya, app):
    as_lenya.get("/m/2026/8")
    month_id = _month_id(app, 2026, 8)

    _add_entry(as_lenya, app, month_id)
    html = as_lenya.get("/m/2026/8").get_data(as_text=True)
    assert "Квартира" in html and "500,00" in html and "ожидает" in html

    with app.app_context():
        entry = Entry.query.filter_by(name="Квартира").first()
        entry_id, group_id = entry.id, entry.group_id

    as_lenya.post(f"/entries/{entry_id}/toggle")
    assert "оплачено" in as_lenya.get("/m/2026/8").get_data(as_text=True)

    as_lenya.post(f"/entries/{entry_id}/update", data={
        "name": "Квартира", "amount": "520,00", "group_id": group_id, "tag_id": "",
    })
    assert "520,00" in as_lenya.get("/m/2026/8").get_data(as_text=True)

    as_lenya.post(f"/entries/{entry_id}/delete")
    html = as_lenya.get("/m/2026/8").get_data(as_text=True)
    assert f"edit={entry_id}" not in html  # ledger row gone (name may remain in history)
    with app.app_context():
        assert Entry.query.count() == 0

    with app.app_context():
        messages = [a.message for a in AuditLog.query.all()]
    assert any("добавлено «Квартира»" in m for m in messages)
    assert any("отмечено как оплачено" in m for m in messages)
    assert any("520,00" in m for m in messages)
    assert any("удалено «Квартира»" in m for m in messages)


def test_copy_month_resets_statuses(as_lenya, app):
    as_lenya.get("/m/2026/7")
    july_id = _month_id(app, 2026, 7)
    _add_entry(as_lenya, app, july_id, name="Интернет", amount="29,99")
    with app.app_context():
        entry = Entry.query.filter_by(name="Интернет").first()
        entry_id = entry.id
    as_lenya.post(f"/entries/{entry_id}/toggle")  # mark paid in July

    as_lenya.get("/m/2026/8")
    as_lenya.post("/m/2026/8/copy-prev")

    with app.app_context():
        august = Month.query.filter_by(year=2026, month=8).first()
        copied = Entry.query.filter_by(month_id=august.id).all()
        assert len(copied) == 1
        assert copied[0].name == "Интернет"
        assert copied[0].status == "pending"
        messages = [a.message for a in AuditLog.query.all()]
    assert any("создан Август 2026 из июля" in m for m in messages)


def test_income_updates_current_and_future_months_only(as_lenya, app):
    as_lenya.get("/m/2026/7")
    as_lenya.get("/m/2026/8")
    as_lenya.get("/m/2026/9")
    august_id = _month_id(app, 2026, 8)
    with app.app_context():
        lenya = User.query.filter_by(side="left").first()
        lenya_id = lenya.id

    as_lenya.post(f"/settings/income/{lenya_id}", data={
        "month_id": august_id, "amount": "2 993,00",
    })

    with app.app_context():
        amounts = {}
        for y, m in [(2026, 7), (2026, 8), (2026, 9)]:
            month = Month.query.filter_by(year=y, month=m).first()
            income = MonthIncome.query.filter_by(month_id=month.id, user_id=lenya_id).first()
            amounts[m] = income.amount_cents
    assert amounts[7] == 0          # past untouched
    assert amounts[8] == 299_300    # viewed month updated
    assert amounts[9] == 299_300    # future updated


def test_settlement_line_rendered(as_lenya, app):
    as_lenya.get("/m/2026/8")
    month_id = _month_id(app, 2026, 8)
    with app.app_context():
        lenya = User.query.filter_by(side="left").first()
        anya = User.query.filter_by(side="right").first()
        lenya_id, anya_id = lenya.id, anya.id

    as_lenya.post(f"/settings/income/{lenya_id}", data={"month_id": month_id, "amount": "2993"})
    as_lenya.post(f"/settings/income/{anya_id}", data={"month_id": month_id, "amount": "574"})
    _add_entry(as_lenya, app, month_id, name="Все расходы Лёни", amount="1 799,50", side="left")
    _add_entry(as_lenya, app, month_id, name="Все расходы Ани", amount="1 150,50", side="right")

    html = as_lenya.get("/m/2026/8").get_data(as_text=True)
    assert "Лёня отправит Ане" in html
    assert "885,00" in html
    assert "−576,50" in html  # Аня's negative leftover in the summary table
    # after the transfer both have 308,50; August has 31 days -> 9,95 per day
    assert "Свободно" in html
    assert "308,50" in html
    assert "(9,95 в день)" in html


def test_identity_device_fallback(client, app):
    response = client.get("/m/2026/8")
    cookie_headers = [h for h in response.headers.getlist("Set-Cookie") if "device_id=" in h]
    assert cookie_headers  # device cookie issued when no email header

    html = response.get_data(as_text=True)
    assert "Гость" in html  # user chip falls back


def test_unknown_email_shown_as_guest(client, app):
    client.environ_base["HTTP_X_FORWARDED_EMAIL"] = "stranger@example.com"
    html = client.get("/m/2026/8").get_data(as_text=True)
    assert "Гость" in html
    assert "stranger@example.com" not in html


def test_mock_auth_identifies_user_without_header(app):
    app.config["MOCK_AUTH_EMAIL"] = "lenya@example.com"
    client = app.test_client()
    html = client.get("/m/2026/8").get_data(as_text=True)
    assert ">\n      Лёня\n    </button>" in html or "Лёня" in html
    assert "Гость" not in html
    # a real proxy header still wins over the mock
    html = client.get("/m/2026/8", headers={"X-Forwarded-Email": "anya@example.com"}).get_data(as_text=True)
    assert "Гость" not in html


def test_prefs_saved_per_user(as_lenya, app):
    as_lenya.post("/prefs", data={"accent": "coral", "theme": "dark"})
    with app.app_context():
        lenya = User.query.filter_by(side="left").first()
        assert lenya.accent_color == "coral"
        assert lenya.theme == "dark"
        anya = User.query.filter_by(side="right").first()
        assert anya.accent_color == "teal"

    html = as_lenya.get("/m/2026/8").get_data(as_text=True)
    assert 'data-theme="dark"' in html
    assert 'data-accent="coral"' in html

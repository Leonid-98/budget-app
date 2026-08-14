from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from . import db
from .models import AuditLog, Entry, Month, MonthIncome

MONTHS_NOM = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
              "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]
MONTHS_SHORT = ["янв", "фев", "мар", "апр", "мая", "июн",
                "июл", "авг", "сен", "окт", "ноя", "дек"]

# Entry states: (key, label, css class). A state is either a payment status
# or the bank where the money sits.
STATUSES = [
    ("paid", "оплачено", "good"),
    ("pending", "ожидает", "warn"),
    ("swed", "swedbank", "st-swed"),
    ("coop", "coop pank", "st-coop"),
    ("seb", "seb pank", "st-seb"),
    ("big", "bigbank", "st-big"),
]
STATUS_LABEL = {key: label for key, label, _ in STATUSES}
STATUS_CLASS = {key: cls for key, _, cls in STATUSES}


# ---------- money ----------

def parse_amount(raw):
    """'2 993,00' | '11,5' | '10.25' -> integer cents. Raises ValueError."""
    cleaned = (raw or "").replace(" ", "").replace(" ", "").replace(",", ".")
    if not cleaned:
        raise ValueError(raw)
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(raw)
    cents = (value * 100).to_integral_value(rounding=ROUND_HALF_UP)
    return int(cents)


def fmt_money(cents):
    sign = "−" if cents < 0 else ""
    cents = abs(cents)
    whole, frac = divmod(cents, 100)
    grouped = f"{whole:,}".replace(",", " ")
    return f"{sign}{grouped},{frac:02d}"


# ---------- calendar ----------

def month_label(year, month):
    return f"{MONTHS_NOM[month - 1]} {year}"


def prev_ym(year, month):
    return (year - 1, 12) if month == 1 else (year, month - 1)


def next_ym(year, month):
    return (year + 1, 1) if month == 12 else (year, month + 1)


def fmt_when(dt):
    now = datetime.now()
    if dt.date() == now.date():
        return f"Сегодня {dt:%H:%M}"
    label = f"{dt.day:02d} {MONTHS_SHORT[dt.month - 1]} {dt:%H:%M}"
    if dt.year != now.year:
        label = f"{dt.day:02d} {MONTHS_SHORT[dt.month - 1]} {dt.year} {dt:%H:%M}"
    return label


def ru_plural(n, one, few, many):
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


# ---------- settlement ----------

def settlement(income_left, expenses_left, income_right, expenses_right, ratio):
    """Both persons end up with the same share of the total free money.

    Returns (free_left, free_right, transfer); transfer > 0 means the left
    person sends `transfer` to the right person, < 0 the other way round.
    """
    free_left = income_left - expenses_left
    free_right = income_right - expenses_right
    pool = free_left + free_right
    target_left = int((Decimal(pool) * Decimal(ratio)).to_integral_value(rounding=ROUND_HALF_UP))
    return free_left, free_right, free_left - target_left


# ---------- months ----------

def ensure_month(year, month):
    """Get or create the month row; new months take income from the latest
    existing month before them (or 0)."""
    from .models import User

    row = Month.query.filter_by(year=year, month=month).first()
    if row:
        return row

    row = Month(year=year, month=month)
    db.session.add(row)
    db.session.flush()

    source = (
        Month.query
        .filter((Month.year * 100 + Month.month) < year * 100 + month)
        .order_by((Month.year * 100 + Month.month).desc())
        .first()
    )
    for user in User.query.all():
        amount = 0
        if source:
            prev_income = MonthIncome.query.filter_by(month_id=source.id, user_id=user.id).first()
            amount = prev_income.amount_cents if prev_income else 0
        db.session.add(MonthIncome(month_id=row.id, user_id=user.id, amount_cents=amount))
    db.session.commit()
    return row


def copy_month(target, source, actor):
    """Copy entries and incomes from source month into (empty) target month;
    statuses reset to pending."""
    entries = Entry.query.filter_by(month_id=source.id).order_by(Entry.sort_order, Entry.id).all()
    for e in entries:
        db.session.add(Entry(
            month_id=target.id, user_id=e.user_id, group_id=e.group_id,
            name=e.name, amount_cents=e.amount_cents, status="pending",
            sort_order=e.sort_order,
        ))
    for income in MonthIncome.query.filter_by(month_id=source.id).all():
        target_income = MonthIncome.query.filter_by(month_id=target.id, user_id=income.user_id).first()
        if target_income:
            target_income.amount_cents = income.amount_cents

    count = len(entries)
    word = ru_plural(count, "запись", "записи", "записей")
    log(actor,
        f"создан {month_label(target.year, target.month)} из {MONTHS_GEN[source.month - 1]} "
        f"(скопировано {count} {word}, статусы сброшены)")
    db.session.commit()
    return count


# ---------- audit ----------

def log(actor, message, month_label_value=None):
    db.session.add(AuditLog(actor=actor, message=message, month_label=month_label_value))


def recent_audit():
    """Audit entries from the current and previous calendar month; full log
    stays in the table."""
    today = date.today()
    year, month = prev_ym(today.year, today.month)
    cutoff = datetime(year, month, 1)
    return (AuditLog.query
            .filter(AuditLog.at >= cutoff)
            .order_by(AuditLog.at.desc(), AuditLog.id.desc())
            .all())

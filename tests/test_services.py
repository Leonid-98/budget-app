import pytest

from app.services import fmt_money, parse_amount, settlement


# Real numbers from the family's August sheet ("Траты - Август.csv").
AUGUST = {
    "income_left": 299_300,   # Лёня 2 993,00
    "expenses_left": 179_950,  # 1 799,50
    "income_right": 57_400,   # Аня 574,00
    "expenses_right": 115_050,  # 1 150,50
}


def test_settlement_matches_real_sheet():
    free_l, free_r, transfer = settlement(
        AUGUST["income_left"], AUGUST["expenses_left"],
        AUGUST["income_right"], AUGUST["expenses_right"], "0.5",
    )
    assert free_l == 119_350       # Лёня свободных до перевода
    assert free_r == -57_650       # Аня в минусе — формула это переживает
    assert transfer == 88_500      # Лёня отправит Ане 885,00 (Пропорция в таблице)
    # after the transfer both hold the sheet's Остаток: 308,50
    assert free_l - transfer == 30_850
    assert free_r + transfer == 30_850


def test_settlement_direction_flips():
    _, _, transfer = settlement(50_000, 0, 200_000, 0, "0.5")
    assert transfer == -75_000  # right person sends left


def test_settlement_zero_when_equal():
    _, _, transfer = settlement(100_000, 20_000, 100_000, 20_000, "0.5")
    assert transfer == 0


def test_settlement_custom_ratio():
    # 60/40: left keeps 60% of the pool
    free_l, free_r, transfer = settlement(100_000, 0, 0, 0, "0.6")
    assert free_l - transfer == 60_000
    assert free_r + transfer == 40_000


@pytest.mark.parametrize("raw, cents", [
    ("11,5", 1_150),
    ("11.5", 1_150),
    ("2 993,00", 299_300),
    ("10", 1_000),
    ("0,01", 1),
])
def test_parse_amount(raw, cents):
    assert parse_amount(raw) == cents


@pytest.mark.parametrize("raw", ["", "abc", "1,2,3"])
def test_parse_amount_rejects_garbage(raw):
    with pytest.raises(ValueError):
        parse_amount(raw)


@pytest.mark.parametrize("cents, text", [
    (299_300, "2 993,00"),
    (-57_650, "−576,50"),
    (0, "0,00"),
    (100_000_000, "1 000 000,00"),
])
def test_fmt_money(cents, text):
    assert fmt_money(cents) == text

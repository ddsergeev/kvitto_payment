import pytest

from app.main import build_schedule, calc_discount


def test_calc_discount_no_promo():
    """Тест без промокода"""
    assert calc_discount(1_990_000, None) == 0
    assert calc_discount(1_990_000, "") == 0
    assert calc_discount(1_990_000, "   ") == 0


def test_calc_discount_case_insensitive():
    """Тест промокода в разных регистрах"""
    for code in ("KVITTO10", "kvitto10", " KvItTo10 "):
        assert calc_discount(1_990_000, code) == 199_000  # 10% от standard
        assert calc_discount(990_000, code) == 99_000  # 10% от basic


@pytest.mark.parametrize(
    "amount,months",
    [
        (1_990_000, 3),
        (1_990_000, 6),
        (1_990_000, 12),
        (1_791_000, 3),  # standard с промокодом
        (1_791_000, 6),
        (1_791_000, 12),
        (990_000, 12),
        (2_990_000, 6),
        (1, 3),  # граничный случай: одна копейка на три платежа
    ],
)
def test_build_schedule_invariants(amount, months):
    schedule = build_schedule(amount, months)
    assert sum(schedule) == amount  # сумма графика равна сумме к оплате
    assert len(schedule) == months
    assert max(schedule) - min(schedule) <= 1  # платежи отличаются не больше чем на копейку
    assert schedule[0] >= schedule[-1]  # лишние копейки — в первых платежах

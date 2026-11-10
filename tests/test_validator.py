"""Validation layer: contradictions blocked, entailed claims supported,
inventions blocked as unsupported."""
import datetime as dt

from verba import claims as C
from verba.validator import Validator, SUPPORTED, CONTRADICTED, UNSUPPORTED


def v(store, claim):
    return Validator(store).validate([claim]).verdicts[0]


def test_closed_sundays_contradicted_by_booking(store):
    verdict = v(store, C.closed_weekday("sunday"))
    assert verdict.status == CONTRADICTED
    assert any("2026-12-13" in r for r in verdict.reasons)


def test_closed_weekday_supported_when_true(store):
    # after cancelling the Sunday booking, the universal claim becomes true
    store.cancel_booking("booking_b7")
    assert v(store, C.closed_weekday("sunday")).status == SUPPORTED


def test_allergen_free_blocked_for_pesto(store):
    assert v(store, C.allergen_free("pesto_pasta", "Nut")).status == CONTRADICTED


def test_allergen_free_supported_for_salad(store):
    assert v(store, C.allergen_free("house_salad", "Nut")).status == SUPPORTED


def test_unknown_item_is_unsupported_not_wrong(store):
    assert v(store, C.allergen_free("lobster_ravioli", "Nut")).status == UNSUPPORTED


def test_free_cancellation_window(store):
    assert v(store, C.free_cancellation(2)).status == CONTRADICTED
    assert v(store, C.free_cancellation(48)).status == SUPPORTED


def test_booking_cross_check(store):
    claim = C.booking_confirmed(dt.date(2026, 12, 19), "19:00", 4)
    assert v(store, claim).status == SUPPORTED   # B3 really is in the state
    hallucinated = C.booking_confirmed(dt.date(2026, 12, 19), "20:00", 9)
    assert v(store, hallucinated).status == CONTRADICTED


def test_availability_checks_capacity_and_hours(store):
    assert v(store, C.available(dt.date(2026, 12, 19), "19:30", 2)).status == SUPPORTED
    # party above max party size
    assert v(store, C.available(dt.date(2026, 12, 19), "19:30", 20)).status == CONTRADICTED
    # outside opening hours
    assert v(store, C.available(dt.date(2026, 12, 19), "23:30", 2)).status == CONTRADICTED
    # closed day (plain Sunday, no booking or override)
    assert v(store, C.available(dt.date(2026, 12, 20), "12:00", 2)).status == CONTRADICTED

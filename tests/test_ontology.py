"""Ontology layer: representation, inference, write-time consistency."""
import datetime as dt

import pytest

from verba.ontology import ConsistencyError


def test_regular_hours_loaded(store):
    hours = store.regular_hours()
    assert hours["monday"] == ("11:00", "22:00")
    assert "sunday" not in hours  # the naive conclusion the demo defeats


def test_rdfs_allergen_closure(store):
    allergens = {a for m in store.menu() if m["id"] == "pesto_pasta"
                 for a in m["allergens"]}
    # pine nuts -> PineNut, and via subclass inference TreeNut, Nut, Allergen
    assert {"PineNut", "TreeNut", "Nut", "Allergen"} <= allergens


def test_item_has_allergen_via_subclass(store):
    assert store.item_has_allergen("pesto_pasta", "Nut")       # the demo query
    assert store.item_has_allergen("pesto_pasta", "TreeNut")
    assert not store.item_has_allergen("house_salad", "Nut")
    assert not store.item_has_allergen("house_salad", "Dairy")


def test_diet_inference(store):
    diets = {m["id"]: m["diets"] for m in store.menu()}
    assert "Vegan" in diets["house_salad"]
    assert "Vegetarian" in diets["margherita_pizza"]
    assert "Vegan" not in diets["margherita_pizza"]      # mozzarella (Dairy)
    assert "Vegetarian" not in diets["grilled_salmon"]   # Fish


def test_booking_entails_opening(store):
    openings = store.openings_on_weekday("sunday")
    assert len(openings) == 1
    date, start, end, reason = openings[0]
    assert date == dt.date(2026, 12, 13)
    assert (start, end) == ("18:00", "23:00")
    assert "Rao" in reason


def test_opening_for_regular_and_closed_days(store):
    assert store.opening_for_date(dt.date(2026, 12, 13))["open"]       # Sunday booking
    assert store.opening_for_date(dt.date(2026, 12, 14))["open"]       # Monday regular
    assert not store.opening_for_date(dt.date(2026, 12, 20))["open"]   # plain Sunday


def test_closure_rejected_when_confirmed_booking(store):
    with pytest.raises(ConsistencyError, match="Mehta"):
        store.add_closure(dt.date(2026, 12, 19))
    # rollback: model unchanged, booking still there, day still open
    assert store.opening_for_date(dt.date(2026, 12, 19))["open"]
    assert store.confirmed_bookings(dt.date(2026, 12, 19))


def test_closure_accepted_on_quiet_day(store):
    store.add_closure(dt.date(2026, 12, 25))
    assert not store.opening_for_date(dt.date(2026, 12, 25))["open"]


def test_special_opening_propagates(store):
    store.add_special_opening(dt.date(2026, 12, 20), "10:00", "14:00", "brunch")
    info = store.opening_for_date(dt.date(2026, 12, 20))
    assert info["open"] and info["start"] == "10:00"
    assert store.openings_on_weekday("sunday")  # now visible to the weekday query


def test_cancel_booking_retracts_derived_opening(store):
    assert store.cancel_booking("booking_b7")
    assert store.openings_on_weekday("sunday") == []
    assert not store.cancel_booking("booking_b7")  # already cancelled


def test_model_starts_consistent(store):
    assert store.consistency_violations() == []

"""The validation layer: every drafted claim is checked against the model
before the agent is allowed to say it.

Verdicts:
  SUPPORTED    - the inferred model entails the claim. Safe to speak.
  CONTRADICTED - the inferred model entails its negation. Blocked, with the
                 exact model facts responsible (used by the repair stage).
  UNSUPPORTED  - the model says nothing either way. Also blocked: the agent
                 may not improvise facts.

This is the piece plain retrieval (RAG) does not have. RAG fetches relevant
text; it never proves the answer agrees with everything else the business
knows. Here, "closed on Sundays" is blocked not because a keyword matched,
but because a confirmed Sunday booking ENTAILS an opening that the claim
denies.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .claims import Claim
from .ontology import OntologyStore

SUPPORTED = "supported"
CONTRADICTED = "contradicted"
UNSUPPORTED = "unsupported"


@dataclass
class Verdict:
    claim: Claim
    status: str
    reasons: list[str] = field(default_factory=list)

    @property
    def speakable(self) -> bool:
        return self.status == SUPPORTED


@dataclass
class ValidationResult:
    verdicts: list[Verdict]

    @property
    def allowed(self) -> bool:
        return all(v.speakable for v in self.verdicts)

    @property
    def blocked(self) -> list[Verdict]:
        return [v for v in self.verdicts if not v.speakable]


class Validator:
    def __init__(self, store: OntologyStore):
        self.store = store

    def validate(self, claims: list[Claim]) -> ValidationResult:
        return ValidationResult([self._check(c) for c in claims])

    # ------------------------------------------------------------ internals
    def _check(self, claim: Claim) -> Verdict:
        handler = getattr(self, f"_check_{claim.kind}", None)
        if handler is None:
            return Verdict(claim, UNSUPPORTED, [f"no rule for claim kind '{claim.kind}'"])
        return handler(claim)

    def _check_closed_weekday(self, claim: Claim) -> Verdict:
        weekday = claim.slots["weekday"]
        openings = self.store.openings_on_weekday(weekday)
        if openings:
            reasons = [
                f"model contains an opening on {weekday.capitalize()} "
                f"{d.isoformat()} {start}-{end} ({reason})"
                for (d, start, end, reason) in openings
            ]
            return Verdict(claim, CONTRADICTED, reasons)
        if weekday in self.store.regular_hours():
            start, end = self.store.regular_hours()[weekday]
            return Verdict(claim, CONTRADICTED,
                           [f"regular hours list {weekday} {start}-{end}"])
        return Verdict(claim, SUPPORTED, [f"no hours or openings on any {weekday}"])

    def _check_open_date(self, claim: Claim) -> Verdict:
        date = claim.slots["date"]
        info = self.store.opening_for_date(date)
        if info is None or not info["open"]:
            return Verdict(claim, CONTRADICTED,
                           [f"model lists {date.isoformat()} as closed ({info and info['source']})"])
        return Verdict(claim, SUPPORTED,
                       [f"{date.isoformat()} open {info['start']}-{info['end']} ({info['source']})"])

    def _check_closed_date(self, claim: Claim) -> Verdict:
        date = claim.slots["date"]
        info = self.store.opening_for_date(date)
        if info and info["open"]:
            return Verdict(claim, CONTRADICTED,
                           [f"model lists {date.isoformat()} open {info['start']}-{info['end']} ({info['source']})"])
        return Verdict(claim, SUPPORTED, [f"{date.isoformat()} closed ({info['source']})"])

    def _check_allergen_free(self, claim: Claim) -> Verdict:
        item, allergen = claim.slots["item"], claim.slots["allergen"]
        if not self._known_item(item):
            return Verdict(claim, UNSUPPORTED, [f"'{item}' is not on the menu"])
        if self.store.item_has_allergen(item, allergen):
            found = [a for a in self._item_allergens(item)]
            return Verdict(claim, CONTRADICTED,
                           [f"{item} carries allergen class '{allergen}' (allergens: {', '.join(found)})"])
        return Verdict(claim, SUPPORTED, [f"no '{allergen}' anywhere under {item}'s ingredients"])

    def _check_contains_allergen(self, claim: Claim) -> Verdict:
        item, allergen = claim.slots["item"], claim.slots["allergen"]
        if not self._known_item(item):
            return Verdict(claim, UNSUPPORTED, [f"'{item}' is not on the menu"])
        if self.store.item_has_allergen(item, allergen):
            return Verdict(claim, SUPPORTED, [f"{item} carries '{allergen}' via ingredient classes"])
        return Verdict(claim, CONTRADICTED, [f"{item} has no '{allergen}' in the model"])

    def _check_suitable_diet(self, claim: Claim) -> Verdict:
        item, diet = claim.slots["item"], claim.slots["diet"].capitalize()
        if not self._known_item(item):
            return Verdict(claim, UNSUPPORTED, [f"'{item}' is not on the menu"])
        diets = {d for m in self.store.menu() if m["id"] == item for d in m["diets"]}
        if diet in diets:
            return Verdict(claim, SUPPORTED, [f"{item} tagged {diet} by diet rules"])
        return Verdict(claim, CONTRADICTED, [f"{item} is not {diet} per the model"])

    def _check_free_cancellation(self, claim: Claim) -> Verdict:
        hours_before = claim.slots["hours_before"]
        pol = self.store.cancellation_policy()
        if hours_before >= pol["free_hours"]:
            return Verdict(claim, SUPPORTED,
                           [f"policy allows free cancellation >= {pol['free_hours']}h before"])
        return Verdict(claim, CONTRADICTED,
                       [f"policy: free cancellation only >= {pol['free_hours']}h before; "
                        f"inside that, fee ${pol['late_fee']}"])

    def _check_available(self, claim: Claim) -> Verdict:
        date, start, party = claim.slots["date"], claim.slots["start"], claim.slots["party"]
        cap = self.store.capacity()
        if party > cap["max_party"]:
            return Verdict(claim, CONTRADICTED,
                           [f"party of {party} exceeds max party size {cap['max_party']}"])
        info = self.store.opening_for_date(date)
        if not info or not info["open"]:
            return Verdict(claim, CONTRADICTED, [f"{date.isoformat()} is closed"])
        if not (info["start"] <= start < info["end"]):
            return Verdict(claim, CONTRADICTED,
                           [f"{start} is outside opening hours {info['start']}-{info['end']}"])
        covers = sum(b["party"] for b in self.store.confirmed_bookings(date)
                     if b["start"][:2] == start[:2])
        if covers + party > cap["max_covers"]:
            return Verdict(claim, CONTRADICTED,
                           [f"slot full: {covers}/{cap['max_covers']} covers already booked"])
        return Verdict(claim, SUPPORTED,
                       [f"{covers + party}/{cap['max_covers']} covers after booking"])

    def _check_booking_confirmed(self, claim: Claim) -> Verdict:
        """The booking cross-check: the agent may only SAY a booking exists
        if the booking state actually contains it."""
        date, start, party = claim.slots["date"], claim.slots["start"], claim.slots["party"]
        for b in self.store.confirmed_bookings(date):
            if b["start"] == start and b["party"] == party:
                return Verdict(claim, SUPPORTED, [f"booking state holds {b['id']} for that slot"])
        return Verdict(claim, CONTRADICTED,
                       ["no matching confirmed booking in the model - never claimed to the caller"])

    def _check_on_menu(self, claim: Claim) -> Verdict:
        item = claim.slots["item"]
        if self._known_item(item):
            return Verdict(claim, SUPPORTED, [f"'{item}' is on the menu"])
        return Verdict(claim, UNSUPPORTED, [f"'{item}' is not on the menu"])

    # helpers
    def _known_item(self, item: str) -> bool:
        return any(m["id"] == item for m in self.store.menu())

    def _item_allergens(self, item: str) -> list[str]:
        for m in self.store.menu():
            if m["id"] == item:
                return m["allergens"]
        return []

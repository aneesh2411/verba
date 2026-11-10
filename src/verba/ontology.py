"""Verba ontology store.

One RDF graph is the single source of truth for a business: hours, menu,
allergens, policies, bookings, notes. Both channels (voice + owner chat)
read and write through this store, so the two can never drift apart.

Reasoning is hybrid, deliberately:
  - rdflib + owlrl OWL-RL/RDFS closure handles class/subclass semantics
    (pine nut -> tree nut -> nut -> allergen) and materializes types.
  - A small set of documented Python rules handles what OWL cannot:
    calendar arithmetic (a confirmed booking on a date entails the
    business is open for that interval) and closure-by-negation for
    diets (vegan = contains no animal product).

Consistency constraints are enforced at write time: an owner update that
would contradict the model (e.g. closing a date that holds a confirmed
booking) is rejected with an explanation, not silently merged.
"""
from __future__ import annotations

import datetime as dt
import itertools
from pathlib import Path

import owlrl
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

V = Namespace("https://verba.dev/ontology#")

WEEKDAYS = [
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
]

_counter = itertools.count(1)


def _fresh(graph: Graph, prefix: str) -> URIRef:
    """Mint a new instance URI that does not collide with the graph."""
    while True:
        candidate = V[f"{prefix}_{next(_counter)}"]
        if (candidate, None, None) not in graph:
            return candidate


class ConsistencyError(ValueError):
    """Raised when an update would make the model inconsistent."""


class OntologyStore:
    """Loads the business model, materializes inference, guards writes."""

    def __init__(self, ttl_path: str | Path):
        self.ttl_path = Path(ttl_path)
        self.graph = Graph()
        self.graph.parse(self.ttl_path, format="turtle")
        self.graph.bind("", V)
        self.infer()

    # ---------------------------------------------------------- inference
    def infer(self) -> None:
        """Materialize OWL-RL closure, then run domain rules to fixpoint."""
        g = self.graph
        owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g)
        before = -1
        while len(g) != before:
            before = len(g)
            self._rule_allergen_closure()
            self._rule_diet_tags()
            self._rule_openings_from_bookings()
            self._rule_openings_from_overrides()

    def _rule_allergen_closure(self) -> None:
        """dish contains ingredient i, i is a kind of Allergen -> dish hasAllergen A.

        Because RDFS closure already materialized every superclass type of i,
        "i is a kind of Allergen" is a plain type lookup here.
        """
        g = self.graph
        for dish, ingredient in list(g.subject_objects(V.contains)):
            for allergen in g.objects(ingredient, RDF.type):
                if (allergen, RDFS.subClassOf, V.Allergen) in g or allergen == V.Allergen:
                    g.add((dish, V.hasAllergen, allergen))

    def _rule_diet_tags(self) -> None:
        """Negation-as-failure diet rules over the closed world of the menu.

        vegan      := contains no ingredient that is an AnimalProduct
        vegetarian := contains no ingredient that is Meat or Fish
        """
        g = self.graph
        for item in g.subjects(RDF.type, V.MenuItem):
            ingredients = list(g.objects(item, V.contains))
            types = set()
            for ing in ingredients:
                types |= set(g.objects(ing, RDF.type))
            if not any((t, RDFS.subClassOf, V.AnimalProduct) in g or t == V.AnimalProduct for t in types):
                g.add((item, V.dietTag, V.Vegan))
            if not any(t in (V.Meat, V.Fish) for t in types):
                g.add((item, V.dietTag, V.Vegetarian))

    def _rule_openings_from_bookings(self) -> None:
        """A confirmed booking entails the business is open for its interval.

        This is the rule a JSON schema cannot express: it relates two
        different slices of the model (bookings and hours) and is what makes
        "closed on Sundays" provably false when a Sunday booking exists.
        Idempotent: skips bookings that already have a derived opening.
        """
        g = self.graph
        for booking in g.subjects(RDF.type, V.ConfirmedBooking):
            if list(g.subjects(V.derivedFrom, booking)):
                continue
            date = g.value(booking, V.onDate)
            start = g.value(booking, V.opensAt)
            end = g.value(booking, V.closesAt)
            if date is None or start is None or end is None:
                continue
            opening = _fresh(g, "opening")
            g.add((opening, RDF.type, V.OpenInterval))
            g.add((opening, V.onDate, date))
            g.add((opening, V.opensAt, start))
            g.add((opening, V.closesAt, end))
            g.add((opening, V.derivedFrom, booking))

    def _rule_openings_from_overrides(self) -> None:
        """A special-opening HoursOverride entails an OpenInterval."""
        g = self.graph
        for override in g.subjects(RDF.type, V.HoursOverride):
            if list(g.subjects(V.derivedFrom, override)):
                continue
            date = g.value(override, V.onDate)
            start = g.value(override, V.opensAt)
            end = g.value(override, V.closesAt)
            if date is None or start is None or end is None:
                continue
            opening = _fresh(g, "opening")
            g.add((opening, RDF.type, V.OpenInterval))
            g.add((opening, V.onDate, date))
            g.add((opening, V.opensAt, start))
            g.add((opening, V.closesAt, end))
            g.add((opening, V.derivedFrom, override))

    # -------------------------------------------------------- consistency
    def consistency_violations(self) -> list[str]:
        """Date-level contradictions a schema would never notice."""
        g = self.graph
        violations: list[str] = []
        closure_dates = {d for d in g.objects(None, V.onDate)
                         for s in g.subjects(V.onDate, d)
                         if (s, RDF.type, V.ClosureNotice) in g}
        for d in sorted(closure_dates):
            for booking in g.subjects(RDF.type, V.ConfirmedBooking):
                if g.value(booking, V.onDate) == d:
                    name = g.value(booking, V.bookingName)
                    violations.append(
                        f"ClosureNotice on {d} conflicts with confirmed booking "
                        f"'{name}' on the same date"
                    )
            for opening in g.subjects(RDF.type, V.OpenInterval):
                if g.value(opening, V.onDate) != d:
                    continue
                source = g.value(opening, V.derivedFrom)
                if source is not None and (source, RDF.type, V.ConfirmedBooking) in g:
                    continue  # already reported as the booking conflict above
                label = g.value(source, V.text) if source is not None else None
                violations.append(
                    f"ClosureNotice on {d} conflicts with an opening on the same date"
                    + (f" ({label})" if label else "")
                )
        return violations

    # ------------------------------------------------------------- reads
    def regular_hours(self) -> dict[str, tuple[str, str]]:
        g = self.graph
        out: dict[str, tuple[str, str]] = {}
        for h in g.subjects(RDF.type, V.RegularHours):
            day = g.value(h, V.openWeekday)
            if day is not None:
                out[str(day)] = (str(g.value(h, V.opensAt)), str(g.value(h, V.closesAt)))
        return out

    def openings_on_weekday(self, weekday: str) -> list[tuple[dt.date, str, str, str]]:
        """OpenIntervals (booking- or override-derived) falling on a weekday."""
        g = self.graph
        out = []
        for o in g.subjects(RDF.type, V.OpenInterval):
            d = g.value(o, V.onDate)
            if d is None:
                continue
            date = d.toPython() if hasattr(d, "toPython") else d
            if WEEKDAYS[date.weekday()] != weekday:
                continue
            source = g.value(o, V.derivedFrom)
            reason = ""
            if source is not None:
                reason = str(g.value(source, V.bookingName) or
                             g.value(source, V.text) or "special opening")
            out.append((date, str(g.value(o, V.opensAt)), str(g.value(o, V.closesAt)), reason))
        return sorted(out)

    def opening_for_date(self, date: dt.date) -> dict | None:
        """Effective opening for one date, with precedence: closure > override > regular.

        Returns {open: bool, start, end, source} or None if the model says nothing.
        """
        g = self.graph
        weekday = WEEKDAYS[date.weekday()]
        for c in g.subjects(RDF.type, V.ClosureNotice):
            if g.value(c, V.onDate) == Literal(date):
                return {"open": False, "start": None, "end": None, "source": "closure notice"}
        for o in g.subjects(RDF.type, V.OpenInterval):
            if g.value(o, V.onDate) == Literal(date):
                return {"open": True, "start": str(g.value(o, V.opensAt)),
                        "end": str(g.value(o, V.closesAt)), "source": "special opening"}
        regular = self.regular_hours()
        if weekday in regular:
            start, end = regular[weekday]
            return {"open": True, "start": start, "end": end, "source": "regular hours"}
        return {"open": False, "start": None, "end": None, "source": "no hours listed"}

    def confirmed_bookings(self, date: dt.date | None = None) -> list[dict]:
        g = self.graph
        out = []
        for b in g.subjects(RDF.type, V.ConfirmedBooking):
            d = g.value(b, V.onDate)
            pydate = d.toPython() if d is not None and hasattr(d, "toPython") else None
            if date is not None and pydate != date:
                continue
            out.append({
                "id": str(b).split("#")[-1],
                "name": str(g.value(b, V.bookingName) or "guest"),
                "date": pydate,
                "start": str(g.value(b, V.opensAt)),
                "end": str(g.value(b, V.closesAt)),
                "party": int(g.value(b, V.partySize)),
            })
        return sorted(out, key=lambda r: (r["date"], r["start"]))

    def menu(self) -> list[dict]:
        g = self.graph
        items = []
        for m in g.subjects(RDF.type, V.MenuItem):
            items.append({
                "id": str(m).split("#")[-1],
                "name": str(g.value(m, V.name)),
                "price": str(g.value(m, V.price)),
                "allergens": sorted({str(a).split("#")[-1] for a in g.objects(m, V.hasAllergen)}),
                "diets": sorted({str(t).split("#")[-1] for t in g.objects(m, V.dietTag)}),
            })
        return sorted(items, key=lambda r: r["name"])

    def item_has_allergen(self, item_id: str, allergen: str) -> bool:
        """True if the item carries the allergen OR any subclass of it."""
        g = self.graph
        item = V[item_id]
        target = V[allergen]
        for a in g.objects(item, V.hasAllergen):
            if a == target or (a, RDFS.subClassOf, target) in g:
                return True
        return False

    def notes(self) -> list[str]:
        return [str(t) for t in self.graph.objects(None, V.text)
                for s in self.graph.subjects(V.text, t)
                if (s, RDF.type, V.Note) in self.graph]

    def cancellation_policy(self) -> dict:
        g = self.graph
        pol = next(g.subjects(RDF.type, V.CancellationPolicy))
        return {
            "free_hours": int(g.value(pol, V.freeCancellationHours)),
            "late_fee": str(g.value(pol, V.lateCancellationFee)),
        }

    def capacity(self) -> dict:
        g = self.graph
        biz = next(g.subjects(RDF.type, V.Business))
        return {
            "max_party": int(g.value(biz, V.maxPartySize)),
            "max_covers": int(g.value(biz, V.maxCoversPerSlot)),
        }

    # ------------------------------------------------------------ writes
    def add_special_opening(self, date: dt.date, start: str, end: str,
                            label: str = "special opening") -> None:
        self._require_consistent_future(
            lambda: self._add_opening_triples(date, start, end, label),
            date,
        )

    def _add_opening_triples(self, date, start, end, label):
        g = self.graph
        o = _fresh(g, "override")
        g.add((o, RDF.type, V.HoursOverride))
        g.add((o, V.onDate, Literal(date)))
        g.add((o, V.opensAt, Literal(start)))
        g.add((o, V.closesAt, Literal(end)))
        g.add((o, V.text, Literal(label)))

    def add_closure(self, date: dt.date) -> None:
        def add():
            g = self.graph
            c = _fresh(g, "closure")
            g.add((c, RDF.type, V.ClosureNotice))
            g.add((c, V.onDate, Literal(date)))
        self._require_consistent_future(add, date)

    def add_note(self, text: str) -> None:
        g = self.graph
        n = _fresh(g, "note")
        g.add((n, RDF.type, V.Note))
        g.add((n, V.text, Literal(text)))

    def add_booking(self, name: str, date: dt.date, start: str, end: str,
                    party: int) -> str:
        g = self.graph
        b = _fresh(g, "booking")
        g.add((b, RDF.type, V.ConfirmedBooking))
        g.add((b, V.bookingName, Literal(name)))
        g.add((b, V.onDate, Literal(date)))
        g.add((b, V.opensAt, Literal(start)))
        g.add((b, V.closesAt, Literal(end)))
        g.add((b, V.partySize, Literal(party)))
        self.infer()
        return str(b).split("#")[-1]

    def cancel_booking(self, booking_id: str) -> bool:
        g = self.graph
        b = V[booking_id]
        if (b, RDF.type, V.ConfirmedBooking) not in g:
            return False
        g.remove((b, RDF.type, V.ConfirmedBooking))
        g.add((b, RDF.type, V.CancelledBooking))
        # Derived openings from this booking are no longer entailed; drop them.
        for opening in list(g.subjects(V.derivedFrom, b)):
            g.remove((opening, None, None))
        self.infer()
        return True

    def _require_consistent_future(self, mutate, date: dt.date) -> None:
        """Apply a write only if the resulting model stays consistent.

        The write is staged, the full consistency check runs, and on any
        violation the graph is rolled back: bad state never becomes truth.
        """
        snapshot = self.graph.serialize(format="turtle")
        mutate()
        self.infer()
        violations = self.consistency_violations()
        if violations:
            self.graph = Graph()
            self.graph.parse(data=snapshot, format="turtle")
            self.graph.bind("", V)
            raise ConsistencyError("; ".join(violations))

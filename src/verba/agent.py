"""The agent core: deterministic NLU + draft/validate/repair.

Honesty note (also in the README): there is no live LLM here. The `naive`
draft is scripted and deliberately emulates the mistake a plain
retrieve-and-paraphrase bot makes - it overgeneralizes from retrieval hits
("no Sunday hours found" -> "closed on Sundays"). That mistake is the input
the validation layer exists to catch. In production, the drafter is an LLM;
validate and repair stay exactly as they are.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from . import claims as C
from .ontology import OntologyStore, ConsistencyError, WEEKDAYS
from .validator import Validator


@dataclass
class Turn:
    speaker: str           # "caller" | "owner" | "agent"
    text: str
    blocked: list[str] = field(default_factory=list)


@dataclass
class Reply:
    text: str
    claims: list = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    naive_draft: str | None = None     # what a plain RAG bot would have said


WEEKDAY_ALIASES = {w: w for w in WEEKDAYS} | {
    "mon": "monday", "tue": "tuesday", "tues": "tuesday", "wed": "wednesday",
    "thu": "thursday", "thur": "thursday", "thurs": "thursday",
    "fri": "friday", "sat": "saturday", "sun": "sunday",
}

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul",
     "aug", "sep", "oct", "nov", "dec"], start=1)}

ITEM_ALIASES = {
    "margherita": "margherita_pizza", "pizza": "margherita_pizza",
    "pesto pasta": "pesto_pasta", "pesto": "pesto_pasta", "pasta": "pesto_pasta",
    "salmon": "grilled_salmon", "salad": "house_salad",
    "tiramisu": "tiramisu",
}

ALLERGEN_ALIASES = {
    "tree nuts": "TreeNut", "tree nut": "TreeNut", "nuts": "Nut", "nut": "Nut",
    "peanuts": "Peanut", "peanut": "Peanut", "dairy": "Dairy", "milk": "Dairy",
    "gluten": "Gluten", "wheat": "Gluten", "eggs": "Egg", "egg": "Egg",
}

READABLE_CLASS = {"TreeNut": "tree nuts", "Nut": "nuts", "PineNut": "pine nuts",
                  "Peanut": "peanuts", "Dairy": "dairy", "Gluten": "gluten",
                  "Egg": "eggs", "Allergen": "allergens"}


def parse_date(text: str, today: dt.date) -> dt.date | None:
    """'sunday(s)', 'this friday', 'dec 20', 'december 20' -> date."""
    t = text.lower()
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})", t)
    if m:
        month = MONTHS[m.group(1)]
        day = int(m.group(2))
        year = today.year + (1 if (month, day) < (today.month, today.day) else 0)
        return dt.date(year, month, day)
    for alias, weekday in sorted(WEEKDAY_ALIASES.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{alias}s?\b", t):
            target = WEEKDAYS.index(weekday)
            delta = (target - today.weekday()) % 7
            if "next" in t and delta == 0:
                delta = 7
            return today + dt.timedelta(days=delta)
    if "today" in t:
        return today
    if "tomorrow" in t:
        return today + dt.timedelta(days=1)
    return None


def parse_time(text: str) -> str | None:
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text.lower())
    if m:
        h = int(m.group(1)) % 12
        if m.group(3) == "pm":
            h += 12
        return f"{h:02d}:{m.group(2) or '00'}"
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None


class VerbaAgent:
    """One brain, shared by every channel. Holds the ontology store."""

    def __init__(self, store: OntologyStore, today: dt.date | None = None):
        self.store = store
        self.validator = Validator(store)
        self.today = today or dt.date.today()

    # ---------------------------------------------------------- answering
    def answer_caller(self, utterance: str) -> Reply:
        t = utterance.lower()

        if "cancel" in t and re.search(r"\b(policy|fee|charge|free|hours?)\b", t):
            return self._cancellation_policy(t)
        if re.search(r"\bcancel\b", t) and re.search(r"\b(booking|table|reservation)\b", t):
            return self._cancel_booking(t)
        if re.search(r"\b(book|reserve|table for|reservation)\b", t):
            return self._make_booking(t)
        if re.search(r"\b(vegan|vegetarian)\b", t):
            return self._diet(t)
        if ("free" in t and re.search(r"\b(allerg|nuts?|peanuts?|dairy|gluten|wheat|eggs?)\b", t)) \
                or re.search(r"\b(does|is|are)\b.*\b(contain|have)\b.*\b(nuts?|peanuts?|dairy|gluten|eggs?)\b", t):
            return self._allergen(t)
        if re.search(r"\b(menu|serve|dishes|eat|food)\b", t):
            return self._menu()
        if re.search(r"\b(park|parking)\b", t):
            return self._parking()
        if re.search(r"\b(open|close|hours)\b", t):
            return self._hours(t)
        return Reply(text=("I'm sorry, I didn't catch that. You can ask me about our "
                           "hours, menu, allergens, or bookings."))

    # ---------------------------------------------------------- handlers
    def _hours(self, t: str) -> Reply:
        date = parse_date(t, self.today)
        if date is None:
            lines = []
            regular = self.store.regular_hours()
            for day in WEEKDAYS:
                hours = regular.get(day)
                lines.append(f"  {day.capitalize():9s} "
                             + (f"{hours[0]}-{hours[1]}" if hours else "closed"))
            return Reply(text="Our regular hours are:\n" + "\n".join(lines))

        weekday = WEEKDAYS[date.weekday()]
        info = self.store.opening_for_date(date)
        universal = "every" in t or re.search(rf"\b{weekday}s\b", t) is not None
        regular = self.store.regular_hours()
        naive = (f"We're closed on {weekday.capitalize()}s."
                 if weekday not in regular
                 else f"We're open {regular[weekday][0]} to {regular[weekday][1]} "
                      f"on {weekday.capitalize()}s.")

        if info["open"]:
            claim = C.open_date(date, info["start"], info["end"])
            self.validator.validate([claim])  # entailed by construction
            return Reply(text=(f"Yes, we're open on {date.strftime('%A, %B %-d')} "
                               f"from {info['start']} to {info['end']}."),
                         claims=[claim], naive_draft=naive)

        claim = C.closed_weekday(weekday) if universal else C.closed_date(date)
        result = self.validator.validate([claim])
        if result.allowed:
            return Reply(text=f"No, we're closed on {date.strftime('%A, %B %-d')}.",
                         claims=[claim], naive_draft=naive)

        # blocked - repair with the exact model facts that blocked it
        reasons = [r for v in result.blocked for r in v.reasons]
        openings = self.store.openings_on_weekday(weekday)
        if openings:
            d, start, end, reason = openings[0]
            repaired = (f"We're usually closed on {weekday.capitalize()}s, but on "
                        f"{d.strftime('%A, %B %-d')} we're open from {start} to {end} "
                        f"({reason}).")
        else:
            repaired = f"We're closed on {date.strftime('%A, %B %-d')} ({info['source']})."
        return Reply(text=repaired, claims=[claim], blocked=reasons, naive_draft=naive)

    def _allergen(self, t: str) -> Reply:
        item = next((v for k, v in sorted(ITEM_ALIASES.items(), key=lambda kv: -len(kv[0]))
                     if k in t), None)
        allergen = next((v for k, v in sorted(ALLERGEN_ALIASES.items(), key=lambda kv: -len(kv[0]))
                         if re.search(rf"\b{re.escape(k)}\b", t)), None)
        if not item or not allergen:
            return Reply(text="Which dish and which allergen would you like me to check?")
        claim = C.allergen_free(item, allergen)
        result = self.validator.validate([claim])
        name = item.replace("_", " ")
        naive = f"Yes, our {name} is {allergen.lower()}-free."
        if result.allowed:
            return Reply(text=naive, claims=[claim], naive_draft=naive)
        reasons = [r for v in result.blocked for r in v.reasons]
        found = [READABLE_CLASS.get(a, a.lower()) for a in self._item_allergens(item)
                 if a != "Allergen"]
        alternatives = [m["name"] for m in self.store.menu()
                        if not self.store.item_has_allergen(m["id"], allergen)][:2]
        suggestion = f" You could go with the {' or the '.join(alternatives)} instead." \
            if alternatives else ""
        repaired = (f"No - our {name} contains {READABLE_CLASS[allergen]} according to our "
                    f"records (listed allergens: {', '.join(found)}).{suggestion}")
        return Reply(text=repaired, claims=[claim], blocked=reasons, naive_draft=naive)

    def _diet(self, t: str) -> Reply:
        diet = "Vegan" if "vegan" in t else "Vegetarian"
        matching = [m["name"] for m in self.store.menu() if diet in m["diets"]]
        if not matching:
            return Reply(text=f"I'm afraid we don't have {diet.lower()} options right now.")
        return Reply(text=f"Our {diet.lower()} options: {', '.join(matching)}.")

    def _menu(self) -> Reply:
        lines = []
        for m in self.store.menu():
            line = f"  {m['name']} (${m['price']})"
            if m["allergens"]:
                shown = [READABLE_CLASS.get(a, a.lower()) for a in m["allergens"]
                         if a != "Allergen"]
                line += f" - allergens: {', '.join(shown)}"
            lines.append(line)
        return Reply(text="Tonight's menu:\n" + "\n".join(lines))

    def _parking(self) -> Reply:
        notes = self.store.notes()
        if notes:
            return Reply(text=" ".join(notes))
        return Reply(text="I don't have parking information yet, sorry.")

    def _cancellation_policy(self, t: str) -> Reply:
        m = re.search(r"(\d+)\s*(?:hours?|h)\b", t)
        pol = self.store.cancellation_policy()
        if m is None:
            return Reply(text=(f"Cancellation is free up to {pol['free_hours']} hours before "
                               f"your booking; inside that window there's a ${pol['late_fee']} fee."))
        hours_before = float(m.group(1))
        claim = C.free_cancellation(hours_before)
        result = self.validator.validate([claim])
        naive = f"Yes, you can cancel free of charge {int(hours_before)} hours before."
        if result.allowed:
            return Reply(text=naive, claims=[claim], naive_draft=naive)
        reasons = [r for v in result.blocked for r in v.reasons]
        repaired = (f"No - free cancellation ends {pol['free_hours']} hours before the booking. "
                    f"Cancelling {int(hours_before)} hours before carries a ${pol['late_fee']} fee.")
        return Reply(text=repaired, claims=[claim], blocked=reasons, naive_draft=naive)

    def _make_booking(self, t: str) -> Reply:
        m = re.search(r"(?:table for|party of)\s+(\d+)", t)
        party = int(m.group(1)) if m else 2
        date = parse_date(t, self.today)
        start = parse_time(t)
        if date is None or start is None:
            return Reply(text="Happy to book that - which day and time did you have in mind?")
        claim = C.available(date, start, party)
        result = self.validator.validate([claim])
        if not result.allowed:
            reasons = [r for v in result.blocked for r in v.reasons]
            info = self.store.opening_for_date(date)
            suggestion = (f" We're open {info['start']}-{info['end']} that day."
                          if info and info["open"] else "")
            return Reply(text=(f"I'm sorry, I can't book a party of {party} on "
                               f"{date.strftime('%A, %B %-d')} at {start}."
                               f"{suggestion}"), claims=[claim], blocked=reasons)
        # State write first, THEN speak the confirmation, validated against state.
        end = f"{int(start[:2]) + 2:02d}:{start[3:]}"
        booking_id = self.store.add_booking("phone guest", date, start, end, party)
        confirm = C.booking_confirmed(date, start, party)
        check = self.validator.validate([confirm])
        if not check.allowed:  # defensive: never tell the caller a booking we don't hold
            return Reply(text="Something went wrong recording that booking - please hold.",
                         claims=[confirm], blocked=["booking cross-check failed"])
        return Reply(text=(f"You're all set - a table for {party} on "
                           f"{date.strftime('%A, %B %-d')} at {start}. "
                           f"Booking reference {booking_id}."),
                     claims=[claim, confirm])

    def _cancel_booking(self, t: str) -> Reply:
        m = re.search(r"\b(b\d+)\b", t)
        if not m:
            return Reply(text="What's the booking reference? It looks like 'b12'.")
        if self.store.cancel_booking(m.group(1)):
            return Reply(text=f"Done - booking {m.group(1)} is cancelled.")
        return Reply(text=f"I couldn't find a confirmed booking '{m.group(1)}'.")

    def _item_allergens(self, item: str) -> list[str]:
        for mi in self.store.menu():
            if mi["id"] == item:
                return mi["allergens"]
        return []

    # ---------------------------------------------------------- owner side
    def handle_owner_message(self, text: str) -> Reply:
        t = text.lower().strip()
        if re.search(r"\b(missed|today'?s calls|what calls)\b", t):
            return Reply(text="__CALL_LOG__")  # resolved by the channel, which owns the log
        m = re.match(r"(?:we'?re |we are )?open (?:on )?(.+?)\s+from\s+(.+?)\s+"
                     r"(?:to|until|-)\s+(.+?)(?:\s+for\s+(.+))?$", t)
        if m:
            date = parse_date(m.group(1), self.today)
            start, end = parse_time(m.group(2)), parse_time(m.group(3))
            label = m.group(4) or "special opening"
            if not date or not start or not end:
                return Reply(text=("I couldn't parse that. Try: "
                                   "\"open sunday dec 20 from 10am to 2pm for brunch\"."))
            try:
                self.store.add_special_opening(date, start, end, label)
            except ConsistencyError as e:
                return Reply(text=f"I can't do that: {e}", blocked=[str(e)])
            return Reply(text=(f"Done - {date.strftime('%A, %B %-d')} is now listed open "
                               f"{start}-{end} ({label}). The phone agent knows already."))
        m = re.match(r"(?:we'?re |we are )?closed (?:on )?(.+)$", t)
        if m:
            date = parse_date(m.group(1), self.today)
            if not date:
                return Reply(text="I couldn't parse the date. Try: \"closed friday dec 18\".")
            try:
                self.store.add_closure(date)
            except ConsistencyError as e:
                return Reply(text=f"I can't do that: {e}", blocked=[str(e)])
            return Reply(text=f"Done - {date.strftime('%A, %B %-d')} is marked closed everywhere.")
        m = re.match(r"(?:add )?note[:\-]?\s+(.+)$", t)
        if m:
            self.store.add_note(m.group(1))
            return Reply(text="Noted - the phone agent will use that from now on.")
        return Reply(text=("I can help with: 'what calls did I miss today?', "
                           "'open sunday dec 20 from 10am to 2pm for brunch', "
                           "'closed friday dec 18', or 'note: ...'."))

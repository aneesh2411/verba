"""Structured claims: what an answer asserts, in a form the validator can check.

The agent never speaks raw text directly. Every drafted answer is first
decomposed into typed claims with slots. The validator then asks the model
two questions per claim: is it CONTRADICTED (must block), and is it
SUPPORTED (safe to say). A claim that is neither is unsupported and also
blocked - the agent may not invent facts.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Claim:
    kind: str
    slots: dict = field(default_factory=dict)

    def describe(self) -> str:
        s = ", ".join(f"{k}={v}" for k, v in self.slots.items())
        return f"{self.kind}({s})"


# Claim kinds (see validator.py for the checks each one maps to):
#   closed_weekday   {weekday}          "we are closed on Sundays"
#   open_date        {date, start, end} "we are open 10:00-14:00 on Dec 20"
#   closed_date      {date}             "we are closed on Dec 19"
#   allergen_free    {item, allergen}   "the pesto is nut-free"
#   contains_allergen{item, allergen}   "the pesto contains tree nuts"
#   suitable_diet    {item, diet}       "the salad is vegan"
#   free_cancellation{hours_before}     "you can cancel free of charge 1h before"
#   booking_confirmed{date, start, party} "your table for 2 is booked"
#   available        {date, start, party} "we can take a party of 2 at 19:00"
#   on_menu          {item}             "we serve Margherita Pizza"

def closed_weekday(weekday: str) -> Claim:
    return Claim("closed_weekday", {"weekday": weekday.lower()})


def open_date(date: dt.date, start: str, end: str) -> Claim:
    return Claim("open_date", {"date": date, "start": start, "end": end})


def closed_date(date: dt.date) -> Claim:
    return Claim("closed_date", {"date": date})


def allergen_free(item: str, allergen: str) -> Claim:
    return Claim("allergen_free", {"item": item, "allergen": allergen})


def contains_allergen(item: str, allergen: str) -> Claim:
    return Claim("contains_allergen", {"item": item, "allergen": allergen})


def suitable_diet(item: str, diet: str) -> Claim:
    return Claim("suitable_diet", {"item": item, "diet": diet})


def free_cancellation(hours_before: float) -> Claim:
    return Claim("free_cancellation", {"hours_before": hours_before})


def booking_confirmed(date: dt.date, start: str, party: int) -> Claim:
    return Claim("booking_confirmed", {"date": date, "start": start, "party": party})


def available(date: dt.date, start: str, party: int) -> Claim:
    return Claim("available", {"date": date, "start": start, "party": party})


def on_menu(item: str) -> Claim:
    return Claim("on_menu", {"item": item})

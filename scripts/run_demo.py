#!/usr/bin/env python3
"""Verba signature demo - runnable end to end, no services, no keys.

Scenario (all dates real): Trattoria Luce, open Mon-Sat 11:00-22:00.
The model holds a CONFIRMED private-event booking on Sunday 2026-12-13.

Act 1 - A caller asks "are you open on Sundays?". The naive draft says
"We're closed on Sundays." The validator catches the contradiction with
the Sunday booking and the agent speaks the repaired, true answer.
Act 2 - Allergen reasoning through the class hierarchy (pine nut -> tree nut).
Act 3 - Cancellation policy check.
Act 4 - A booking is made; the confirmation claim is cross-checked against
actual booking state before it is spoken.
Act 5 - The owner chats in: "what calls did I miss?", then opens Sunday
Dec 20 for brunch. The NEXT caller hears the new hours - one ontology,
two channels, no drift.
Act 6 - The owner tries to close Saturday Dec 19, which has a confirmed
booking. The write is rejected as inconsistent. The booking survives.
Act 7 - A question the model cannot answer is flagged for the owner
instead of improvised; the owner teaches the model and the next caller
gets a real answer.
"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from verba.agent import VerbaAgent
from verba.channels.owner_chat import OwnerChatChannel
from verba.channels.voice import VoiceChannel
from verba.ontology import OntologyStore
from verba.state import CallLog

TODAY = dt.date(2026, 11, 10)  # pinned so the demo is reproducible


def banner(title: str) -> None:
    print()
    print("=" * 74)
    print(title)
    print("=" * 74)


def main() -> int:
    store = OntologyStore(Path(__file__).resolve().parent.parent
                          / "ontology" / "business.ttl")
    agent = VerbaAgent(store, today=TODAY)
    log = CallLog()
    voice = VoiceChannel(agent, log)
    owner = OwnerChatChannel(agent, log)

    # a missed call from earlier in the day, for the owner's "missed calls?"
    log.add("+1-555-0134", "missed", "asked about Friday availability, no voicemail",
            at=dt.datetime(2026, 11, 10, 18, 42))

    banner("ACT 1 - The signature catch: 'closed on Sundays' vs a Sunday booking")
    print("Model facts: no regular Sunday hours; CONFIRMED booking Sun Dec 13")
    print("(Rao holiday party, 40 guests). A plain RAG bot retrieves 'no Sunday")
    print("hours' and overgeneralizes. Watch the validator block it:")
    voice.run_call("+1-555-0177", ["Are you open on Sundays?"],
                   summary="Sunday hours question",
                   at=dt.datetime(2026, 11, 10, 19, 5))

    banner("ACT 2 - Allergen entailment (pine nut -> tree nut -> nut)")
    voice.run_call("+1-555-0182", ["Is the pesto nut-free?"],
                   summary="nut allergy question",
                   at=dt.datetime(2026, 11, 10, 19, 11))

    banner("ACT 3 - Policy check: free cancellation window")
    voice.run_call("+1-555-0190",
                   ["Can I cancel my booking for free 2 hours before?"],
                   summary="cancellation policy question",
                   at=dt.datetime(2026, 11, 10, 19, 18))

    banner("ACT 4 - Bookings: completeness gate, then a cross-checked confirm")
    print("The agent refuses to record a booking without name and phone")
    print("(a placeholder like 'not provided' is a valid string unless code")
    print("rejects it - this guardrail lives on the server, not the prompt):")
    voice.run_call("+1-555-0141",
                   ["Can I book a table for 2 on Saturday Dec 19 at 7:30pm?",
                    "Name's Chen, phone 555-0141"],
                   summary="booking request",
                   at=dt.datetime(2026, 11, 10, 19, 24))
    print()
    print("  Bookings now in the model:")
    for b in store.confirmed_bookings():
        print(f"    {b['id']:12s} {b['date']} {b['start']}-{b['end']} "
              f"party of {b['party']} ({b['name']})")

    banner("ACT 5 - Owner chat: missed calls, then a live model update")
    owner.handle("What calls did I miss today?")
    print()
    owner.handle("We're open Sunday Dec 20 from 10am to 2pm for brunch")
    print()
    print("Same minute, new caller on the phone channel:")
    voice.run_call("+1-555-0166", ["Are you open on Sunday Dec 20?"],
                   summary="Sunday brunch hours question",
                   at=dt.datetime(2026, 11, 10, 19, 40))

    banner("ACT 6 - Owner tries to close a day that has a confirmed booking")
    owner.handle("We're closed Saturday Dec 19")
    print()
    print("  The Dec 19 booking survives the rejected write:")
    for b in store.confirmed_bookings(dt.date(2026, 12, 19)):
        print(f"    {b['id']:12s} {b['date']} {b['start']} party of {b['party']} ({b['name']})")

    banner("ACT 7 - Unknown question: flagged for the owner, then taught")
    print("A caller asks something the model does not know. Instead of")
    print("improvising, the agent flags it. The owner sees the flag, teaches")
    print("the model, and the next caller gets a real answer:")
    voice.run_call("+1-555-0159", ["Do you host wine tastings?"],
                   summary="wine tasting question (flagged)",
                   at=dt.datetime(2026, 11, 10, 19, 52))
    print()
    owner.handle("What calls did I miss today?")
    print()
    owner.handle("note: wine tastings every first Thursday, $40 a head")
    print()
    voice.run_call("+1-555-0171", ["Do you host wine tastings?"],
                   summary="wine tasting question (answered)",
                   at=dt.datetime(2026, 11, 10, 20, 5))

    banner("DONE - validator blocked 4 naive answers; 1 owner write rejected; "
           "1 question flagged and taught")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Incident-corpus regression tests.

Each test encodes a real failure mode reported by practitioners running
voice agents in production (see docs/research-notes.md for the sources):
placeholder-name bookings, bookings with no contact info, double-booking
a private event, hallucinating an answer to an unknown question instead
of handing off, and confirming cancellations for bookings that do not
exist. Every test must fail if the corresponding guardrail regresses.
"""
import datetime as dt

from verba.channels.voice import VoiceChannel
from verba.state import CallLog


def test_placeholder_name_is_refused(agent):
    reply = agent.answer_caller(
        "Book a table for 4 on Saturday Dec 19 at 8pm, name is not provided, "
        "phone 555-0188")
    assert "You're all set" not in reply.text
    assert "name" in reply.text.lower()
    bookings = agent.store.confirmed_bookings(dt.date(2026, 12, 19))
    assert not any(b["party"] == 4 and b["start"] == "20:00" for b in bookings)


def test_missing_contact_info_is_refused(agent):
    reply = agent.answer_caller(
        "Can I book a table for 2 on Friday Dec 18 at 7pm?")
    assert "You're all set" not in reply.text
    assert "contact phone number" in reply.text
    assert not agent.store.confirmed_bookings(dt.date(2026, 12, 18))


def test_pending_booking_survives_across_turns(agent):
    first = agent.answer_caller(
        "Can I book a table for 3 on Saturday Dec 19 at 7:30pm?")
    assert "need" in first.text.lower()
    second = agent.answer_caller("Name's Alvarez, phone 555-0123")
    assert "You're all set" in second.text
    bookings = agent.store.confirmed_bookings(dt.date(2026, 12, 19))
    assert any(b["party"] == 3 and b["start"] == "19:30" for b in bookings)


def test_private_event_double_booking_is_refused(agent):
    # The Rao private event holds Sunday Dec 13 18:30-22:00 (40 guests).
    reply = agent.answer_caller(
        "Book a table for 2 on Sunday Dec 13 at 7pm? Name's Park, "
        "phone 555-0166")
    assert "You're all set" not in reply.text
    assert "private event" in reply.text.lower() or "can't book" in reply.text
    assert not any(b["date"] == dt.date(2026, 12, 13) and b["party"] == 2
                   for b in agent.store.confirmed_bookings())


def test_unknown_question_is_flagged_not_improvised(agent):
    log = CallLog()
    voice = VoiceChannel(agent, log, verbose=False) if False else VoiceChannel(agent, log)
    turns = voice.run_call("+1-555-0159", ["Do you host wine tastings?"],
                           summary="wine tasting question", verbose=False,
                           at=dt.datetime(2026, 11, 10, 19, 52))
    agent_line = turns[-1].text
    assert "first thursday" not in agent_line.lower()
    assert log.flags and "wine tastings" in log.flags[0].question.lower()
    assert log.flags[0].caller == "+1-555-0159"


def test_owner_note_teaches_flagged_question(agent):
    first = agent.answer_caller("Do you host wine tastings?")
    assert first.flagged == "Do you host wine tastings?"
    agent.handle_owner_message(
        "note: wine tastings every first Thursday, $40 a head")
    reply = agent.answer_caller("Do you host wine tastings?")
    assert not reply.flagged
    assert "first thursday" in reply.text.lower()
    assert "40" in reply.text


def test_cancelling_unknown_booking_is_refused(agent):
    reply = agent.answer_caller("Cancel my booking b9999")
    assert "couldn't find" in reply.text.lower()

def test_over_capacity_party_refused_end_to_end(agent):
    # Complete details, but the restaurant seats at most 12: the refusal
    # must come from the capacity rule with a speakable reason, and no
    # state may be written.
    reply = agent.answer_caller(
        "Book a table for 20 on Saturday Dec 19 at 7:30pm? Name's Chen, "
        "phone 555-0141")
    assert "You're all set" not in reply.text
    assert "exceeds max party size 12" in reply.text
    assert not any(b["party"] == 20
                   for b in agent.store.confirmed_bookings(dt.date(2026, 12, 19)))


def test_placeholder_name_does_not_poison_pending_slots(agent):
    agent.answer_caller(
        "Book a table for 2 on Saturday Dec 19 at 8pm, name is not provided")
    second = agent.answer_caller("phone 555-0188")
    assert "You're all set" not in second.text        # name still missing
    assert "name" in second.text.lower()
    third = agent.answer_caller("Name's Chen")
    assert "You're all set" in third.text             # real name completes it
    bookings = agent.store.confirmed_bookings(dt.date(2026, 12, 19))
    assert any(b["start"] == "20:00" and "Chen" in b["name"] for b in bookings)

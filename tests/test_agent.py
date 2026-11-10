"""Agent end-to-end: the naive draft is caught, the spoken answer is true."""
import datetime as dt


def test_sunday_contradiction_catch(agent):
    reply = agent.answer_caller("Are you open on Sundays?")
    assert reply.naive_draft == "We're closed on Sundays."   # the RAG answer
    assert reply.blocked                                     # validator fired
    assert "usually closed on Sundays" in reply.text         # repaired truth
    assert "December 13" in reply.text


def test_specific_open_sunday(agent):
    reply = agent.answer_caller("Are you open on Sunday Dec 13?")
    assert "open on Sunday, December 13" in reply.text
    assert "18:00" in reply.text


def test_plain_closed_sunday(agent):
    reply = agent.answer_caller("Are you open on Sunday Dec 20?")
    assert reply.text.startswith("No, we're closed")
    assert not reply.blocked   # true statement passes validation


def test_allergen_answer(agent):
    reply = agent.answer_caller("Is the pesto nut-free?")
    assert reply.blocked
    assert "contains nuts" in reply.text
    assert "Salmon" in reply.text or "Salad" in reply.text


def test_cancellation_policy(agent):
    reply = agent.answer_caller("Can I cancel my booking for free 2 hours before?")
    assert reply.blocked
    assert "24 hours" in reply.text and "25.00" in reply.text


def test_booking_flow_speaks_only_after_state_write(agent):
    reply = agent.answer_caller("Can I book a table for 2 on Saturday Dec 19 at 7:30pm?")
    assert "You're all set" in reply.text
    bookings = agent.store.confirmed_bookings(dt.date(2026, 12, 19))
    assert any(b["start"] == "19:30" and b["party"] == 2 for b in bookings)


def test_booking_refused_when_closed(agent):
    reply = agent.answer_caller("Can I book a table for 2 on Sunday Dec 20 at 7pm?")
    assert "can't book" in reply.text
    assert not any(b["date"] == dt.date(2026, 12, 20)
                   for b in agent.store.confirmed_bookings())


def test_vegan_options_from_diet_inference(agent):
    reply = agent.answer_caller("Do you have any vegan options?")
    assert "House Salad" in reply.text
    assert "Salmon" not in reply.text


def test_owner_update_propagates_to_voice(agent):
    owner = agent.handle_owner_message("We're open Sunday Dec 20 from 10am to 2pm for brunch")
    assert "now listed open" in owner.text
    caller = agent.answer_caller("Are you open on Sunday Dec 20?")
    assert "10:00" in caller.text and "14:00" in caller.text


def test_owner_closure_rejected_with_booking(agent):
    reply = agent.handle_owner_message("We're closed Saturday Dec 19")
    assert "I can't do that" in reply.text
    assert agent.store.confirmed_bookings(dt.date(2026, 12, 19))


def test_owner_note_reaches_caller(agent):
    agent.handle_owner_message("note: validated parking next door is free for diners")
    reply = agent.answer_caller("Where can I park?")
    assert "validated parking next door" in reply.text

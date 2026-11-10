# Research notes - reliability improvements (Nov 2026)

After the core build, we reviewed practitioner discussions and recent
hackathon projects in the voice-agent / agent-reliability space and adopted
the ideas that fit Verba's architecture. Each adopted feature below names
its source. Nothing was copied as code; the sources supplied failure modes
and design patterns, which we re-expressed in Verba's own validator/agent
model and covered with tests.

## Sources

1. **r/aiagents - "Voice agent keeps hallucinating" (testing thread)**
   <https://www.reddit.com/r/aiagents/comments/1nptiw9/>
   Practitioner consensus: the tool/API layer must be the single source of
   truth, and you need synthetic-call test suites with turn-level
   assertions, not vibes. Verba already had the first (the ontology is the
   truth the validator checks against); this motivated the incident-corpus
   test module (`tests/test_incidents.py`), where every failure mode we
   adopted gets a permanent regression test with turn-level assertions.

2. **r/AI_Agents - "5 weeks of real bookings" postmortem**
   <https://www.reddit.com/r/AI_Agents/comments/1vco5m9/>
   Five weeks of a restaurant voice agent taking real bookings. Reported
   failure modes, and what each became in Verba:
   - *Prompt rules break under real callers; server-side rules hold.*
     -> The booking completeness gate lives in `agent.py` code, not in a
        system prompt (Verba has no system prompt at all - simulated LLM -
        so the gate is pure server code by construction).
   - *Bookings recorded with placeholder names like "not provided"*
     (a placeholder is a valid string unless code rejects it).
     -> `_PLACEHOLDERS` blocklist in the completeness gate; placeholder
        names are refused with a speakable reason
        (`test_placeholder_name_is_refused`).
   - *Bookings with no contact info are useless to the restaurant.*
     -> Name and phone are required slots; partial bookings are held as
        pending state across turns instead of being dropped or half-booked
        (`test_missing_contact_info_is_refused`,
        `test_pending_booking_survives_across_turns`).
   - *Refusals need reason strings the agent can actually speak.*
     -> `validator.refusal_line()` joins blocked reasons into one
        speakable sentence; booking refusals now include the reason
        ("...18:00 is outside opening hours 19:00-21:00").
   - *Regression-test every incident before promoting any change.*
     -> `tests/test_incidents.py` - each incident above is a test that
        fails if the guardrail regresses.

3. **r/VoiceAutomationAI - allergen guardrails and hand-off-over-hallucinate**
   <https://www.reddit.com/r/VoiceAutomationAI/comments/1szrxdr/>
   Two ideas adopted:
   - *Safety answers (allergens) must come from structured tables, never
     from the prompt.* Verba already does this (allergen entailment over
     the ontology, Act 2 of the demo); we kept it and cited the thread as
     independent practitioner confirmation.
   - *Low confidence -> hand off: "better to hand off than hallucinate."*
     -> The honest fallback: a question with no grounding in the model is
        **flagged for the owner** (recorded in the call log with caller
        and timestamp), never improvised. The owner sees flags in "what
        calls did I miss today?", teaches the model with a note, and the
        next caller gets the real answer
        (`test_unknown_question_is_flagged_not_improvised`,
        `test_owner_note_teaches_flagged_question`). Demo Act 7.

4. **Self-Evolving-Voice-Workflows (hackathon project)**
   <https://github.com/ayushgupta4897/Self-Evolving-Voice-Workflows>
   Idea adopted: historical failures become regression tests before any
   change is promoted. Same pattern as source 2's incident corpus; we
   implemented it as the incident-corpus module rather than a
   self-modifying pipeline (which would conflict with Verba's "rules in
   code, not in prompts" stance).

## Also adopted from the same research

- **Private-event double-booking check.** Availability now refuses slots
  overlapping a booking marked "private event" (the Rao holiday party
  holds Sunday Dec 13 18:30-23:00), not just slots outside opening hours.
  Practitioners' "server rules hold" principle applied to a case our own
  sample data already contained (`test_private_event_double_booking_is_refused`).

## Explicitly NOT adopted

- **General iMessage bot for the owner channel.** There is no general
  iMessage bot API; the owner chat stays simulated (research-only finding).
- **Self-evolving prompts** (source 4's full pipeline): conflicts with
  keeping behavioral rules in reviewable server code.
- Any paid telephony/LLM integration: out of scope for this prototype.

# Verba - System Design

Verba is a voice agent for small businesses whose spoken answers are
**validated against a formal business ontology before they are said**.
One ontology is the single source of truth for every channel - today a
(simulated) phone line and a (simulated) WhatsApp-style owner chat.

## Why an ontology, and not a schema or plain RAG?

| Approach | What it can do | What it cannot do |
| --- | --- | --- |
| JSON schema extraction | Type-check one answer's shape | Relate two facts (booking vs hours); say when an answer contradicts *other* facts |
| Plain RAG | Retrieve text that looks relevant | Prove the answer agrees with everything else the business knows; refuse to improvise |
| **Verba (ontology + validation)** | Entailment across facts: a confirmed Sunday booking *entails* an opening, which *contradicts* "closed on Sundays" | (needs a modeled domain - that is the honest cost) |

The signature failure only this design catches: the model holds **no regular
Sunday hours** *and* a **confirmed private-event booking on Sunday Dec 13**.
A retrieval-based bot answers "we're closed on Sundays". Verba's validator
blocks that claim because the booking *entails an opening* the claim denies,
and the repair stage answers: "We're usually closed on Sundays, but on
Sunday, December 13 we're open 18:00-23:00 (Rao holiday party)."

## Architecture

```
        caller (phone, simulated)                owner (chat, simulated)
                |                                        |
        VoiceChannel                            OwnerChatChannel
                |                                        |
                +----------------> VerbaAgent <----------+
                              (scripted NLU, no LLM)
                                     |
            draft claims -> Validator -> speak / repair
                                     |
                            OntologyStore (rdflib)
                    ontology/business.ttl + inference + rules
                                     |
                   bookings, hours, menu, policies, notes
```

### 1. Ontology layer (`ontology/business.ttl`, `src/verba/ontology.py`)

The business model is a real RDF/OWL graph (Turtle syntax), loaded with
rdflib. Inference is hybrid, and the design doc is explicit about why:

- **OWL-RL / RDFS closure** (via `owlrl`) handles class semantics:
  `PineNut ⊑ TreeNut ⊑ Nut ⊑ Allergen`, `Dairy ⊑ AnimalProduct`, etc.
  Subclass transitivity and type materialization come free and are *formal*.
- **Python domain rules** handle what OWL cannot express - calendar
  arithmetic and closed-world diet rules:
  - `booking -> opening`: a `ConfirmedBooking` on date D entails an
    `OpenInterval` for its time window. This rule relates two slices of the
    model; a schema cannot state it.
  - `override -> opening`: a special-opening `HoursOverride` entails an
    `OpenInterval` for its date.
  - `allergen closure`: dish *contains* ingredient of class A (A a subclass
    of `Allergen`) -> dish `hasAllergen` A.
  - `diet tags` (negation as failure over the closed menu): vegan = no
    `AnimalProduct` ingredient; vegetarian = no `Meat`/`Fish`.

**Write-time consistency.** Owner updates are staged, the full consistency
check runs (`consistency_violations`), and on any violation the graph rolls
back. Example: "close Saturday Dec 19" is rejected because a confirmed
booking exists on Dec 19 - the model refuses to become untrue.

### 2. Validation layer (`src/verba/claims.py`, `src/verba/validator.py`)

The agent never speaks raw text. A drafted answer is decomposed into typed
**claims** (`closed_weekday`, `allergen_free`, `free_cancellation`,
`booking_confirmed`, `available`, ...). Each claim gets one of three verdicts:

- **SUPPORTED** - the inferred model entails it. Speakable.
- **CONTRADICTED** - the model entails its negation. Blocked, with the exact
  model facts responsible (these feed the repair stage).
- **UNSUPPORTED** - the model says nothing. Also blocked: Verba may not
  improvise facts.

The **booking cross-check** deserves its name: the claim "your table is
booked" is only speakable if the bookings state actually contains a matching
confirmed booking. The confirmation is written to state *first*, then
validated, then spoken.

### 3. Agent core (`src/verba/agent.py`)

Deterministic, scripted NLU - **no live LLM** (no keys in this environment;
same honest pattern as a benchmark harness). Three stages per turn:

1. **draft**: produce a naive answer the way retrieve-and-paraphrase would
   (this stage *deliberately* overgeneralizes - it is the sparring partner
   for the validator).
2. **validate**: every claim through the Validator.
3. **repair**: if blocked, compose the truthful answer from the model facts
   the validator surfaced.

In production, stage 1 is an LLM. Stages 2 and 3 are unchanged.

### 4. Channels (`src/verba/channels/`)

- **VoiceChannel** - text turns stand in for speech (ASR/TTS are the
  simulated part). Runs scripted inbound calls; logs them.
- **OwnerChatChannel** - WhatsApp-style owner chat. Queries ("what calls did
  I miss today?") and writes ("open Sunday Dec 20 from 10am to 2pm for
  brunch", "closed Friday Dec 25", "note: ...") go through the same store
  and the same consistency checks.

Because both channels share one `OntologyStore`, an owner update is true on
the phone line *immediately* - no sync, no drift. That is the second place
the ontology earns its keep.

### 5. Eval (`scripts/run_demo.py`, `scripts/eval.py`)

- `run_demo.py` - seven-act reproducible scenario ending in the signature
  contradiction catch, a live cross-channel update, a rejected
  inconsistent owner write, and the flag-and-teach fallback loop.
- `eval.py` - six probes with known ground truth; scores the naive draft
  vs the validated answer. Current result: **naive 0/6, validated 6/6**.
  CI fails if validated drops below 6/6.

## Production path (not built here)

| Prototype | Production |
| --- | --- |
| Text turns | Twilio Voice (Media Streams) + Deepgram/Whisper ASR + ElevenLabs/Polly TTS |
| Scripted NLU | LLM function-calling; claims become the function schema |
| Owner chat sim | Twilio WhatsApp Business API webhook |
| In-memory store | Graph DB or Postgres + nightly TTL export |
| Python rules | Keep - they are the product |

## Known limits (honest list)

- NLU is pattern matching; phrasing outside the patterns gets a fallback reply.
- Date arithmetic in rules is Python, not OWL - documented, deliberate.
- Consistency is date-level, not minute-level (a closure overlapping one hour
  of a booking is not detected).
- The Pages demo (`docs/index.html`) is a client-side *simulation* of the
  Python prototype's transcript, for reviewers without a Python setup.

## Addendum: reliability gates (Nov 2026, post-research)

Production postmortems (see docs/research-notes.md) converge on one
principle that fits Verba's design: behavioral rules belong in server
code, not prompts. The additions below extend the validator/agent model
in that direction.

### Booking completeness gate (agent layer)

A booking is a state write, so it is gated like one: party size, day/time,
a name and a contact phone are all required before `_make_booking` may
touch the store. A placeholder ("not provided", "unknown", "n/a", ...)
fails the name check - a string being syntactically valid says nothing
about its content, which is exactly the validator's thesis applied to
slots. Partial slots are kept in `_pending` across turns, so "Name's
Chen, phone 555-0141" completes the earlier request instead of starting
over. The refusal speaks the missing items.

### Speakable refusal reasons

The validator already returned structured blocked-reason strings for
contradicted claims; `refusal_line()` now joins them into one sentence
the agent can say, so a refusal is never a bare "can't do that" when the
model knows why.

### Private-event conflict

`_check_available` refuses any requested slot overlapping a confirmed
booking whose label marks a private event (e.g. the Rao holiday party,
Sun Dec 13 18:30-23:00). Without this, "open with a special opening"
would read as "bookable", double-booking a buyout.

### Honest fallback with owner handoff

`answer_caller` ends at `_fallback`: consult owner notes by keyword
overlap; if nothing matches, reply honestly, set `Reply.flagged`, and the
voice channel records a `FlaggedQuestion` (question, caller, timestamp)
in the call log. The owner's missed-calls summary surfaces flags, and a
`note:` teaches the model. The loop closes in demo Act 7 and is pinned by
`test_unknown_question_is_flagged_not_improvised` and
`test_owner_note_teaches_flagged_question`.

### Incident corpus

`tests/test_incidents.py` encodes every adopted production failure mode
as a regression test with turn-level assertions. CI runs it with the rest
of the suite; a guardrail that regresses turns the build red.

### Known limits added by this pack

- Name extraction is a small regex over one or two lowercase words; a
  caller spelling a name letter-by-letter would not parse.
- Keyword overlap for owner notes is literal words, not embeddings; a
  paraphrase with no shared word still flags.
- Pending bookings live in agent memory, not the store; a new process
  forgets them (fine for the demo's call-scoped lifetime).

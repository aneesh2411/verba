# Verba

**A voice agent for small businesses that is not allowed to lie.**
Every answer is validated against a formal business ontology before it is
spoken. One ontology, two channels: the phone line and the owner's chat.

[![CI](https://github.com/aneesh2411/verba/actions/workflows/ci.yml/badge.svg)](https://github.com/aneesh2411/verba/actions/workflows/ci.yml)

- **Live demo (browser simulation):** https://aneesh2411.github.io/verba/
- **Demo video:** [docs/demo.mp4](docs/demo.mp4)
- **Design:** [docs/system-design.md](docs/system-design.md) -
  **Requirements:** [docs/requirements.md](docs/requirements.md)

## The problem

SMB voice agents confidently say wrong things: "we're closed Sundays" while
a private event is booked that Sunday, "the pesto is nut-free" when it has
pine nuts, "cancel anytime for free" when the policy says 24 hours. RAG
retrieves relevant text; nothing checks the answer against *everything else
the business knows*.

## The idea

Keep the business - hours, menu, allergens, policies, bookings, notes - in a
real RDF/OWL ontology. Every drafted answer becomes typed **claims**; a
validator checks each claim against the *inferred* model:

- **SUPPORTED** (the model entails it) -> speakable
- **CONTRADICTED** (the model entails its negation) -> blocked, and the
  blocking facts drive a repaired answer
- **UNSUPPORTED** (the model is silent) -> blocked; the agent may not improvise

The catch that sells it: the model has *no regular Sunday hours* **and** a
*confirmed Sunday booking*. The booking **entails an opening**, so the
universal claim "closed on Sundays" is provably false - a contradiction no
JSON schema or keyword filter can see, because it lives *between* two facts.

The ontology earns its keep a second time on the write side: the owner can
chat with their own agent ("open Sunday Dec 20 from 10am to 2pm for
brunch"), the update is consistency-checked (closing a day with a confirmed
booking is rejected), and the phone channel answers with the new hours in
the same minute. One model, no drift.

## Quickstart

```bash
pip install -r requirements.txt
python scripts/run_demo.py   # the six-act signature demo
python scripts/eval.py       # naive draft 0/5 vs validated 5/5
python -m pytest -q          # 34 tests
```

## What is real vs simulated

| Real (tested) | Simulated (labeled) |
| --- | --- |
| RDF/OWL model + OWL-RL/RDFS inference (rdflib/owlrl) | Telephony: text turns stand in for ASR/TTS |
| Domain rules: booking->opening entailment, allergen closure, diet tags | WhatsApp transport: owner chat is a CLI-style adapter |
| Claim validation with blocking-fact explanations | The "LLM": NLU/drafting is scripted (no API keys here); the validate/repair stages are production-shaped |
| Booking cross-check (speak only what state holds) | GitHub Pages demo is a scripted replay of the Python transcript |
| Write-time consistency with rollback | |
| Cross-channel propagation through one store | |

## What an ontology adds over schema/RAG

A schema types one answer. RAG finds relevant text. Neither can say "this
answer disagrees with a fact three relationships away." The ontology can:
entailment (`PineNut ⊑ TreeNut ⊑ Nut`) plus domain rules (`ConfirmedBooking
on D -> OpenInterval on D`) turn "closed on Sundays" into a *provably false*
statement in the presence of a Sunday booking. Details and the honest cost
(you must model the domain) are in [docs/system-design.md](docs/system-design.md).

## Repo layout

```
ontology/business.ttl     Trattoria Luce: menu, allergens, hours, bookings, policies
src/verba/ontology.py     store, OWL-RL closure, domain rules, write-time consistency
src/verba/claims.py       typed answer claims
src/verba/validator.py    supported / contradicted / unsupported verdicts
src/verba/agent.py        scripted NLU + draft/validate/repair
src/verba/channels/       voice sim + owner chat sim
scripts/run_demo.py       six-act demo (CI-checked)
scripts/eval.py           naive vs validated battery (CI-checked)
tests/                    34 tests
docs/                     design, requirements, Pages sim, demo video
```

## Next steps (documented, not built)

- Real telephony + owner chat via Twilio Voice Media Streams and the Twilio
  WhatsApp Business API (the channels are already adapter-shaped).
- LLM drafter behind the existing claim schema; validate/repair unchanged.
- SHACL for the constraint layer once the rule set outgrows Python.

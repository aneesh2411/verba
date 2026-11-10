# Verba - Requirements

## Functional requirements

### Voice channel (simulated telephony)

- F1. Answer caller questions about opening hours for a weekday or a
  specific date, using regular hours, one-off openings, and closures.
- F2. Answer allergen questions per dish, reasoning over the ingredient ->
  allergen class hierarchy (pine nut -> tree nut -> nut).
- F3. Answer dietary-fit questions (vegan / vegetarian) derived from
  ingredients, not hand-tagged menu flags.
- F4. State the cancellation policy, including whether cancelling N hours
  before is free.
- F5. Take a booking (party size, date, time) only when the model says the
  slot is available (hours + capacity + party limit), write it to state,
  and only then speak the confirmation (booking cross-check).
- F6. Cancel a booking by reference; derived openings are retracted.
- F7. Log every call (answered/missed, summary) for the owner.

### Validation layer

- F8. Every drafted answer is decomposed into typed claims before speaking.
- F9. A claim contradicted by the inferred model is blocked, with the
  responsible model facts returned.
- F10. A claim the model does not support is blocked (no improvisation).
- F11. A blocked answer triggers repair: the agent composes the truthful
  answer from the blocking facts.

### Owner chat channel (simulated WhatsApp)

- F12. Owner can ask for today's calls / missed calls.
- F13. Owner can add a one-off opening ("open Sunday Dec 20 from 10am to
  2pm for brunch"); it is visible to the voice channel immediately.
- F14. Owner can add a one-off closure; the write is **rejected** if it
  conflicts with a confirmed booking or special opening on that date.
- F15. Owner can add a note (parking, wifi, ...); the voice channel uses it.
- F16. Owner updates pass the same consistency checks as any write; bad
  state never becomes truth (stage, check, roll back on violation).

### Eval and demo

- F17. `scripts/run_demo.py` runs the six-act scenario end to end,
  exit code 0, no services or keys.
- F18. `scripts/eval.py` scores naive draft vs validated answer on 5 probes
  with known ground truth; fails unless validated is 5/5.
- F19. A client-side simulation of the demo runs on GitHub Pages for
  reviewers without a Python setup.

## Non-functional requirements

- N1. **Honesty.** Everything simulated is labeled simulated (telephony,
  WhatsApp transport, LLM). Everything claimed real is real and tested
  (ontology, inference, validation, cross-channel propagation).
- N2. **No paid dependencies.** No paid services, no LLM API keys, no
  external accounts. `pip install -r requirements.txt` is all it takes.
- N3. **Determinism.** Demo and eval are reproducible (pinned "today",
  fixed call times). Same input, same transcript.
- N4. **Test coverage.** Every validator claim type, every owner write
  path, and the cross-channel propagation have tests; CI runs them plus
  the demo and the eval on Python 3.11 and 3.12.
- N5. **Latency (prototype).** Validation adds < 200 ms per turn on a
  laptop for the sample model (in-memory graph, no network).
- N6. **Extensibility.** A new claim kind = one method on `Validator`.
  A new domain rule = one method on `OntologyStore`, run to fixpoint.
  A real channel = one adapter implementing the channel interface.
- N7. **Single source of truth.** Channels never hold private copies of
  business facts; all reads and writes go through `OntologyStore`.
- N8. **Auditability.** Every blocked answer carries the machine-readable
  reason (claim + blocking facts), suitable for logs and eval dashboards.

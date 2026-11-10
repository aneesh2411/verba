#!/usr/bin/env python3
"""Verba eval battery: naive draft vs validated answer, scored.

For each probe we know the ground truth from the model. The naive draft
(what a retrieve-and-paraphrase bot would say) is scored against it, then
the validated answer is scored. The delta is the value of the ontology
layer, in numbers, for an interview.
"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from verba.agent import VerbaAgent
from verba.ontology import OntologyStore

TODAY = dt.date(2026, 11, 10)

# probe, substring that makes a naive answer WRONG (its absence in the naive
# answer = naive pass), substring that must appear in the validated answer
PROBES = [
    ("Are you open on Sundays?",
     "closed on Sundays", "usually closed"),
    ("Is the pesto nut-free?",
     "is nut-free", "contains"),
    ("Can I cancel my booking for free 2 hours before?",
     "can cancel free of charge", "24 hours"),
    ("Are you open on Sunday Dec 13?",
     "closed on Sundays", "open on Sunday, December 13"),
    ("Is the pesto pasta gluten-free?",
     "is gluten-free", "contains"),
    ("Do you host wine tastings?",
     "absolutely", "flagged your question"),
]


def main() -> int:
    store = OntologyStore(Path(__file__).resolve().parent.parent
                          / "ontology" / "business.ttl")
    agent = VerbaAgent(store, today=TODAY)

    naive_correct = validated_correct = 0
    print(f"{'probe':52s} {'naive':7s} {'validated':9s}")
    print("-" * 72)
    for probe, naive_tell, truth in PROBES:
        reply = agent.answer_caller(probe)
        naive = reply.naive_draft or "(no draft)"
        naive_ok = naive_tell.lower() not in naive.lower()
        valid_ok = truth.lower() in reply.text.lower()
        naive_correct += naive_ok
        validated_correct += valid_ok
        print(f"{probe[:52]:52s} {'ok' if naive_ok else 'WRONG':7s} "
              f"{'ok' if valid_ok else 'WRONG':9s}")
        if not valid_ok:
            print(f"    expected substring: {truth!r}\n    got: {reply.text!r}")
    print("-" * 72)
    n = len(PROBES)
    print(f"naive draft correct:  {naive_correct}/{n}")
    print(f"validated answer correct: {validated_correct}/{n}")
    return 0 if validated_correct == n else 1


if __name__ == "__main__":
    raise SystemExit(main())

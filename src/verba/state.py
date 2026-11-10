"""Call log shared by the channels.

Bookings live in the ontology itself (they are model facts). The call log is
operational state: which simulated calls came in, whether they were answered,
and one-line summaries the owner can ask about.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass
class CallRecord:
    caller: str
    started_at: dt.datetime
    status: str          # "answered" | "missed"
    summary: str = ""


@dataclass
class CallLog:
    records: list[CallRecord] = field(default_factory=list)

    def add(self, caller: str, status: str, summary: str,
            at: dt.datetime | None = None) -> CallRecord:
        rec = CallRecord(caller=caller, status=status, summary=summary,
                         started_at=at or dt.datetime.now())
        self.records.append(rec)
        return rec

    def missed(self, on: dt.date | None = None) -> list[CallRecord]:
        return [r for r in self.records if r.status == "missed"
                and (on is None or r.started_at.date() == on)]

    def summary_for(self, on: dt.date) -> str:
        day = [r for r in self.records if r.started_at.date() == on]
        missed = [r for r in day if r.status == "missed"]
        lines = [f"Today so far: {len(day)} calls, {len(missed)} missed."]
        for r in day:
            mark = "MISSED" if r.status == "missed" else "answered"
            lines.append(f"  {r.started_at.strftime('%H:%M')} {mark:8s} {r.caller} - {r.summary}")
        return "\n".join(lines)

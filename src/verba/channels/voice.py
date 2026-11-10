"""Simulated voice channel.

Text turns stand in for speech (ASR/TTS are the simulated part - see README).
Everything between the turns is real: the same agent, ontology, validator
and booking state that a production telephony adapter would call.
"""
from __future__ import annotations

from ..agent import VerbaAgent, Turn
from ..state import CallLog


class VoiceChannel:
    def __init__(self, agent: VerbaAgent, log: CallLog):
        self.agent = agent
        self.log = log

    def run_call(self, caller: str, script: list[str],
                 summary: str = "", verbose: bool = True,
                 at=None) -> list[Turn]:
        """Run a scripted inbound call; every caller line gets an agent reply."""
        turns: list[Turn] = []
        for line in script:
            turns.append(Turn("caller", line))
            reply = self.agent.answer_caller(line)
            turns.append(Turn("agent", reply.text, blocked=reply.blocked))
        self.log.add(caller, "answered", summary or script[0][:60], at=at)
        if verbose:
            for turn in turns:
                prefix = "CALLER" if turn.speaker == "caller" else "AGENT "
                print(f"  {prefix}  {turn.text}")
                for reason in turn.blocked:
                    print(f"         [validator blocked naive answer: {reason}]")
        return turns

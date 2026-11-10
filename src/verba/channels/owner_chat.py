"""Simulated owner chat channel (WhatsApp-style).

The transport is simulated (no WhatsApp Business API calls - see README).
The behavior is real: the owner queries call state and mutates the SAME
ontology the voice channel answers from, through the same consistency
checks. An update that lands here is true on the phone immediately.
"""
from __future__ import annotations

from ..agent import VerbaAgent, Turn
from ..state import CallLog


class OwnerChatChannel:
    def __init__(self, agent: VerbaAgent, log: CallLog):
        self.agent = agent
        self.log = log

    def handle(self, message: str, verbose: bool = True) -> Turn:
        reply = self.agent.handle_owner_message(message)
        text = reply.text
        if text == "__CALL_LOG__":
            text = self.log.summary_for(self.agent.today)
        turn = Turn("agent", text, blocked=reply.blocked)
        if verbose:
            print(f"  OWNER   {message}")
            print(f"  VERBA   {text}")
        return turn

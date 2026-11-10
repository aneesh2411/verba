"""Channels: one brain, two surfaces; call log flows to the owner."""
import datetime as dt

from verba.channels.owner_chat import OwnerChatChannel
from verba.channels.voice import VoiceChannel
from verba.state import CallLog


def test_voice_call_logged(agent):
    log = CallLog()
    voice = VoiceChannel(agent, log, )
    voice.run_call("+1-555-0100", ["What are your hours?"], verbose=False)
    assert len(log.records) == 1
    assert log.records[0].status == "answered"


def test_owner_missed_calls_query(agent):
    log = CallLog()
    log.add("+1-555-0134", "missed", "asked about Friday availability",
            at=dt.datetime(2026, 11, 10, 18, 42))
    owner = OwnerChatChannel(agent, log)
    turn = owner.handle("What calls did I miss today?", verbose=False)
    assert "555-0134" in turn.text
    assert "MISSED" in turn.text


def test_channels_share_one_model(agent):
    log = CallLog()
    voice = VoiceChannel(agent, log)
    owner = OwnerChatChannel(agent, log)
    owner.handle("We're closed Friday Dec 25", verbose=False)
    turns = voice.run_call("+1-555-0101", ["Are you open on Friday Dec 25?"],
                           verbose=False)
    agent_says = [t.text for t in turns if t.speaker == "agent"][0]
    assert agent_says.startswith("No, we're closed")

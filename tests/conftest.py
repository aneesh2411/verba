import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from verba.ontology import OntologyStore  # noqa: E402

TODAY = dt.date(2026, 11, 10)
TTL = Path(__file__).resolve().parent.parent / "ontology" / "business.ttl"


@pytest.fixture()
def store():
    return OntologyStore(TTL)


@pytest.fixture()
def agent(store):
    from verba.agent import VerbaAgent
    return VerbaAgent(store, today=TODAY)

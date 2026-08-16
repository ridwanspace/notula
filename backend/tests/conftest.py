"""Global test fixtures. The whole suite must pass with no network and no keys."""

from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail loudly if any test (or the code under test) touches the network."""

    def _blocked(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("network access blocked in tests")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    yield

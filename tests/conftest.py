"""Shared test fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    """Return the raw JSON text of a captured sadf fixture."""
    return (FIXTURE_DIR / f"{name}.json").read_text()


def load_json(name: str) -> dict:
    return json.loads(load_fixture(name))


@pytest.fixture
def fixture_text():
    return load_fixture


@pytest.fixture
def fixture_json():
    return load_json

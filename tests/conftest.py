"""Shared test fixtures."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"

#: sadc lives outside PATH on most distros.
SADC_CANDIDATES = (
    "/usr/libexec/sysstat/sadc",
    "/usr/lib/sysstat/sadc",
    "/usr/lib64/sysstat/sadc",
)


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


def find_sadc() -> str | None:
    for candidate in SADC_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return shutil.which("sadc")


@pytest.fixture(scope="session")
def sar_archive(tmp_path_factory) -> Path:
    """Collect a short, real sysstat archive for end-to-end tests.

    Generated per session rather than read from a path outside the repo, so
    these tests actually run wherever sysstat is installed instead of silently
    skipping on every machine but the one that happened to have a scratch file.
    """
    sadc = find_sadc()
    if sadc is None or shutil.which("sadf") is None:
        pytest.skip("sysstat (sadc/sadf) is not installed")

    archive = tmp_path_factory.mktemp("sar") / "sa_test"
    try:
        subprocess.run(
            [sadc, "-S", "ALL", "1", "3", str(archive)],
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        pytest.skip(f"sadc could not collect an archive: {exc}")

    if not archive.exists():
        pytest.skip("sadc produced no archive")
    return archive

"""Streamlit UI smoke tests via `streamlit.testing.v1.AppTest`.

Runs the real app script headlessly (no browser) and checks it renders
without raising -- this catches import errors, bad `st.*` call
signatures, and broken control flow on initial load. Deeper interaction
testing (clicking "Start investigation" and asserting on the resulting
API call) is intentionally out of scope here: `AppTest` executes the
script in an isolated runner where patching the module-level `httpx`
import from the test process doesn't reliably carry over, and standing
up a live FastAPI server just for a UI smoke test is disproportionate
for this project's scope. Manual verification via `streamlit run
ui/streamlit_app.py` against a running API is the documented path for
that (see README).
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.unit


def test_app_loads_without_raising() -> None:
    at = AppTest.from_file("ui/streamlit_app.py")
    at.run(timeout=15)
    assert not at.exception


def test_app_renders_expected_controls() -> None:
    at = AppTest.from_file("ui/streamlit_app.py")
    at.run(timeout=15)
    assert at.title[0].value == "🛠️ Enterprise Incident Resolution Agent"
    assert len(at.text_area) >= 1
    assert any(b.label == "Start investigation" for b in at.button)


def test_start_button_is_disabled_with_empty_query() -> None:
    at = AppTest.from_file("ui/streamlit_app.py")
    at.run(timeout=15)
    start_button = next(b for b in at.button if b.label == "Start investigation")
    assert start_button.disabled is True

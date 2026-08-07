"""
Cross-module integration tests: real tcb/session_store.py code, real
automation/blinkit_auth.py + blinkit_scraper.py code, only Supabase faked
(see conftest.py's FakeSupabaseClient). Playwright is still mocked here —
that's a genuine external system this repo can't run in CI — but nothing
in the session-store path is mocked.

This is the layer tests/unit/ can't cover: those tests mock
tcb.session_store's own functions directly, which proves each module calls
session_store correctly in isolation, but not that the save from one
script and the load from another actually agree on a real (if faked)
backing store.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import tcb.session_store as session_store
import automation.blinkit_auth as blinkit_auth
import automation.blinkit_scraper as blinkit_scraper

pytestmark = pytest.mark.integration_mocked


def _mock_playwright_cm(storage_state_to_capture):
    """A MagicMock sync_playwright() context manager whose ctx.storage_state()
    returns the given value — used to drive blinkit_auth.py's login flow."""
    p = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = p
    cm.__exit__.return_value = False
    p.chromium.launch.return_value.new_context.return_value.storage_state.return_value = (
        storage_state_to_capture
    )
    return p, cm


class TestSessionStoreRoundTrip:
    """Real session_store.py functions, real Supabase-shaped upsert/select
    semantics via the fake client — not just mocked call assertions."""

    def test_save_then_load_round_trips_through_fake_backend(self, fake_supabase):
        state = {"cookies": [{"name": "sid", "value": "abc"}], "origins": []}

        session_store.save_session("blinkit", state)
        loaded = session_store.load_session("blinkit")

        assert loaded == state

    def test_load_returns_none_before_anything_saved(self, fake_supabase):
        assert session_store.load_session("fc") is None

    def test_second_save_overwrites_first_for_same_portal(self, fake_supabase):
        session_store.save_session("blinkit", {"cookies": [{"name": "a", "value": "1"}], "origins": []})
        session_store.save_session("blinkit", {"cookies": [{"name": "b", "value": "2"}], "origins": []})

        loaded = session_store.load_session("blinkit")
        assert loaded["cookies"] == [{"name": "b", "value": "2"}]

    def test_different_portals_do_not_clobber_each_other(self, fake_supabase):
        blinkit_state = {"cookies": [{"name": "blk", "value": "1"}], "origins": []}
        fc_state = {"cookies": [{"name": "fc", "value": "2"}], "origins": []}

        session_store.save_session("blinkit", blinkit_state)
        session_store.save_session("fc", fc_state)

        assert session_store.load_session("blinkit") == blinkit_state
        assert session_store.load_session("fc") == fc_state


class TestAuthToScraperHandoff:
    """The actual value of this tier: does a real blinkit_auth.py login,
    saving through real session_store code, produce something a real
    blinkit_scraper.py run can genuinely load back and use?"""

    def test_auth_saved_session_is_loadable_by_scraper(
        self, monkeypatch, tmp_path, fake_supabase
    ):
        captured_state = {"cookies": [{"name": "sid", "value": "from-real-login"}], "origins": []}

        # Drive blinkit_auth.py's real run() through to its save_session() call.
        p, cm = _mock_playwright_cm(captured_state)
        monkeypatch.setattr(blinkit_auth, "sync_playwright", MagicMock(return_value=cm))
        monkeypatch.setattr(blinkit_auth.time, "sleep", lambda *a, **k: None)
        monkeypatch.setenv("BLINKIT_USERNAME", "9999999999")

        blinkit_auth.run()

        # Now drive blinkit_scraper.py's real scrape() far enough to confirm
        # it received exactly what auth saved — abort right after via a
        # sentinel exception so the rest of the scrape flow isn't needed.
        monkeypatch.setattr(blinkit_scraper, "DOWNLOAD_DIR", tmp_path)
        p2 = MagicMock()
        cm2 = MagicMock()
        cm2.__enter__.return_value = p2
        cm2.__exit__.return_value = False
        monkeypatch.setattr(blinkit_scraper, "sync_playwright", MagicMock(return_value=cm2))
        p2.chromium.launch.return_value.new_context.side_effect = RuntimeError("stop-here-sentinel")

        with pytest.raises(RuntimeError, match="stop-here-sentinel"):
            blinkit_scraper.scrape()

        _, new_context_kwargs = p2.chromium.launch.return_value.new_context.call_args
        assert new_context_kwargs["storage_state"] == captured_state

"""
Unit tests for the feature flag module (tcb/flags.py).
Mocks database connection completely.
"""

from __future__ import annotations

import os
import time
from unittest import TestCase
from unittest.mock import MagicMock, patch

import pytest

from tcb.flags import _FLAG_CACHE, is_enabled


class TestFeatureFlags(TestCase):

    def setUp(self):
        # Clear the cache before every test to isolate test cases
        _FLAG_CACHE.clear()

    @patch("tcb.db.get_client")
    def test_flag_off_everywhere(self, mock_get_client):
        # Setup mock db query
        mock_res = MagicMock()
        mock_res.data = {"status": "off", "allowed_users": []}
        mock_get_client.return_value.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_res

        # Test in dev
        with patch.dict(os.environ, {"TCB_ENV": "dev"}):
            self.assertFalse(is_enabled("test_flag"))

        # Test in prod
        _FLAG_CACHE.clear()
        with patch.dict(os.environ, {"TCB_ENV": "prod"}):
            self.assertFalse(is_enabled("test_flag"))

    @patch("tcb.db.get_client")
    def test_flag_on_everywhere(self, mock_get_client):
        mock_res = MagicMock()
        mock_res.data = {"status": "on", "allowed_users": []}
        mock_get_client.return_value.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_res

        # Test in dev
        with patch.dict(os.environ, {"TCB_ENV": "dev"}):
            self.assertTrue(is_enabled("test_flag"))

        # Test in prod
        _FLAG_CACHE.clear()
        with patch.dict(os.environ, {"TCB_ENV": "prod"}):
            self.assertTrue(is_enabled("test_flag"))

    @patch("tcb.db.get_client")
    def test_flag_dev_only(self, mock_get_client):
        mock_res = MagicMock()
        mock_res.data = {"status": "dev_only", "allowed_users": []}
        mock_get_client.return_value.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_res

        # Test in dev
        with patch.dict(os.environ, {"TCB_ENV": "dev"}):
            self.assertTrue(is_enabled("test_flag"))

        # Test in prod
        _FLAG_CACHE.clear()
        with patch.dict(os.environ, {"TCB_ENV": "prod"}):
            self.assertFalse(is_enabled("test_flag"))

    @patch("tcb.db.get_client")
    def test_flag_testing(self, mock_get_client):
        mock_res = MagicMock()
        mock_res.data = {"status": "testing", "allowed_users": []}
        mock_get_client.return_value.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_res

        # Test in dev
        with patch.dict(os.environ, {"TCB_ENV": "dev"}):
            self.assertTrue(is_enabled("test_flag"))

        # Test in staging
        _FLAG_CACHE.clear()
        with patch.dict(os.environ, {"TCB_ENV": "staging"}):
            self.assertTrue(is_enabled("test_flag"))

        # Test in prod
        _FLAG_CACHE.clear()
        with patch.dict(os.environ, {"TCB_ENV": "prod"}):
            self.assertFalse(is_enabled("test_flag"))

    @patch("tcb.db.get_client")
    def test_flag_prod_test(self, mock_get_client):
        mock_res = MagicMock()
        mock_res.data = {
            "status": "prod_test",
            "allowed_users": ["himanshu@example.com", "pv@example.com"],
        }
        mock_get_client.return_value.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_res

        # Test in dev (unconditional True)
        with patch.dict(os.environ, {"TCB_ENV": "dev"}):
            self.assertTrue(is_enabled("test_flag"))

        # Test in prod without email (should be False)
        _FLAG_CACHE.clear()
        with patch.dict(os.environ, {"TCB_ENV": "prod"}):
            self.assertFalse(is_enabled("test_flag"))

        # Test in prod with non-whitelisted email (should be False)
        _FLAG_CACHE.clear()
        with patch.dict(os.environ, {"TCB_ENV": "prod"}):
            self.assertFalse(is_enabled("test_flag", user_email="other@example.com"))

        # Test in prod with whitelisted email (case-insensitive checks, should be True)
        _FLAG_CACHE.clear()
        with patch.dict(os.environ, {"TCB_ENV": "prod"}):
            self.assertTrue(is_enabled("test_flag", user_email="HIMANSHU@example.com"))
            self.assertTrue(is_enabled("test_flag", user_email="pv@example.com "))

    @patch("tcb.db.get_client")
    def test_failsafe_on_db_exception(self, mock_get_client):
        # Setup mock db query to raise exception
        mock_get_client.return_value.table.side_effect = Exception("DB Connection Lost")

        with patch.dict(os.environ, {"TCB_ENV": "dev"}):
            # Should fail safely to False, and not raise exception
            self.assertFalse(is_enabled("test_flag"))

    @patch("tcb.db.get_client")
    def test_failsafe_on_missing_flag(self, mock_get_client):
        # Setup mock db query to return None (no row found)
        mock_res = MagicMock()
        mock_res.data = None
        mock_get_client.return_value.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_res

        with patch.dict(os.environ, {"TCB_ENV": "dev"}):
            # Should fail safely to False
            self.assertFalse(is_enabled("test_flag"))

    @patch("tcb.db.get_client")
    def test_ttl_caching(self, mock_get_client):
        mock_res = MagicMock()
        mock_res.data = {"status": "on", "allowed_users": []}
        mock_execute = mock_get_client.return_value.table.return_value.select.return_value.eq.return_value.single.return_value.execute
        mock_execute.return_value = mock_res

        with patch.dict(os.environ, {"TCB_ENV": "dev"}):
            # First call fetches from DB
            self.assertTrue(is_enabled("test_flag"))
            self.assertEqual(mock_execute.call_count, 1)

            # Second call uses cache (execute call_count does not increase)
            self.assertTrue(is_enabled("test_flag"))
            self.assertEqual(mock_execute.call_count, 1)

            # Manually expire the cache in the global dict
            row, expiry = _FLAG_CACHE["test_flag"]
            _FLAG_CACHE["test_flag"] = (row, time.time() - 10)

            # Third call refetches from DB since cache is expired
            self.assertTrue(is_enabled("test_flag"))
            self.assertEqual(mock_execute.call_count, 2)

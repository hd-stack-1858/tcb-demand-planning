"""
tests/unit/ overrides the repo-root conftest.py's autouse `seed_dev_cogs`
fixture — that fixture forces a real dev DB connection, which unit tests
must never require. Everything under tests/unit/ mocks its dependencies
and should be runnable with zero credentials, in any environment.
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def seed_dev_cogs():
    yield

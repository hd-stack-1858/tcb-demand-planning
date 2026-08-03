"""
tests/migrations/ overrides the repo-root conftest.py's autouse `seed_dev_cogs`
fixture — that fixture forces a real dev Supabase connection. The migration
runner tests here exercise psycopg2 against a throwaway schema on whatever
Postgres `TCB_TEST_DB_URL` / `DEV_DB_URL` points at, with no Supabase needed.
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def seed_dev_cogs():
    yield

"""This AI unit-test subtree has no database dependency.

Shadow the repository-wide migration fixture so `pytest tests/test_ai_eval -q`
remains an offline evaluation command and does not migrate the shared test DB.
"""
import pytest


@pytest.fixture(scope="session", autouse=True)
def migrated_test_schema():
    yield

import os

import pytest


@pytest.fixture(scope="session")
def e2e_base_url() -> str:
    return os.getenv("E2E_BASE_URL", "http://localhost:8000").rstrip("/")

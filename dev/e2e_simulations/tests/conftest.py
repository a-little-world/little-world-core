import os

import pytest


@pytest.fixture(scope="session")
def e2e_base_url() -> str:
    return os.getenv("E2E_BASE_URL", "http://localhost:8000").rstrip("/")


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    slow_mo_ms = os.getenv("E2E_SLOW_MO_MS", "").strip()
    if not slow_mo_ms:
        return browser_type_launch_args

    return {
        **browser_type_launch_args,
        "slow_mo": int(slow_mo_ms),
    }

import os

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "needs_mort: requires MORT_HOME (a Mort checkout)")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("MORT_HOME"):
        return
    skip = pytest.mark.skip(reason="set MORT_HOME to a checkout of github.com/0xmortuex/Mort")
    for item in items:
        if "needs_mort" in item.keywords:
            item.add_marker(skip)

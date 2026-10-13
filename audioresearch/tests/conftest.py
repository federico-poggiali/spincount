import pytest


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", help="run tests that touch the network")


def pytest_configure(config):
    config.addinivalue_line("markers", "live: touches the real network; skipped unless --live")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip = pytest.mark.skip(reason="live test: pass --live to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)

"""Require executed PostgreSQL evidence when Application CI loads this plugin."""

import pytest


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    """Fail a database skip without changing unrelated optional test outcomes."""
    test_report = yield
    if item.get_closest_marker("postgres") is not None and (
        test_report.skipped or hasattr(test_report, "wasxfail")
    ):
        test_report.outcome = "failed"
        test_report.longrepr = "PostgreSQL evidence cannot be skipped in Application CI"
        if hasattr(test_report, "wasxfail"):
            del test_report.wasxfail
    return test_report


@pytest.hookimpl(wrapper=True)
def pytest_make_collect_report(collector):
    """Reject skipped modules before they can hide their database markers."""
    collection_report = yield
    if collection_report.skipped:
        collection_report.outcome = "failed"
        collection_report.longrepr = "Application CI requires complete test collection"
    return collection_report

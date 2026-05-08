from __future__ import annotations


def test_worker_modules_importable() -> None:
    # The worker runs with app-local modules (db/models/services) sourced from apps/api.
    # This smoke test ensures the import graph stays intact.
    import main  # noqa: F401
    import jobs  # noqa: F401


def test_ping_job_returns_expected_payload() -> None:
    from jobs import ping_job

    assert ping_job("hello") == "pong:hello"


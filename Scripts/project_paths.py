#!/usr/bin/env python3

"""Project-local path definitions and safety checks."""

from pathlib import Path


SCRIPTS_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_ROOT.parent
TESTDATA_ROOT = (PROJECT_ROOT / "testdata").resolve()
RESULTS_ROOT = (PROJECT_ROOT / "Results").resolve()


def require_testdata_path(candidate):
    """Return an absolute path only when it is inside this project's testdata."""
    resolved = Path(candidate).expanduser().resolve()
    try:
        resolved.relative_to(TESTDATA_ROOT)
    except ValueError as exc:
        raise ValueError(
            "Refusing to access data outside ALTAI_CHIPTEST_NEW/testdata: "
            f"{resolved}"
        ) from exc
    return resolved

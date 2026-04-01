"""Central scheme dataset alias used by runtime response controls.

This module intentionally exposes a single SCHEME_DATA source so
response/routing logic can enforce supported-scheme boundaries.
"""

try:
    from src.utils.scheme_data import SCHEME_DATA  # type: ignore
except Exception:
    from backend.src.utils.scheme_data import SCHEME_DATA  # type: ignore

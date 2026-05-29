"""Compatibility entrypoint for the chronological V1/V2 golden-set benchmark.

The original comparison used future activities while calibrating historical
predictions. Keep this command usable, but delegate to the leakage-safe
benchmark implementation.
"""
from __future__ import annotations

from compare_golden_set import main


if __name__ == "__main__":
    print(
        "compare_v1_v2.py delegates to compare_golden_set.py "
        "(chronological history and target exclusions enabled)."
    )
    main()

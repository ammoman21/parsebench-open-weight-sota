"""
Raw-layout-label instrumentation.

WHY THIS EXISTS. The pipeline turns the model's raw layout label
(`NativeLayoutItem.raw_category`) into a benchmark category through
`NATIVE_LAYOUT_CATEGORY_MAP` inside `_category_for_item`
(`kdl_frontier_nano.py:757-763`). Only the *result* of that lookup is persisted to
run artifacts — the raw label is discarded. That is why the `section_header` map fix
measures as exactly 0 by replay: the evidence needed to evaluate it was thrown away
on the way in.

Consequence: any raw label absent from the 26-key map silently becomes `Text` (the map
has an `"unknown": "Text"` entry and `_map_provider_category` falls back). Elements that
should be `Section-header` are therefore scored as `Text`, which is consistent with
classification being our weakest grounding sub-metric (0.784) while localization is our
strongest (0.869) — the boxes are right, the labels are wrong.

WHAT THIS DOES. Wraps `_category_for_item` to record, for every element:
  raw label · resulting category · whether the raw label was actually present in the map
and writes a per-document JSON sidecar. That single capture makes every map variant
measurable **by replay afterwards**, so the instrumented run is the only GPU time this
question needs.

Enable with `PARSEBENCH_LABEL_CAPTURE=<dir>`; a no-op when unset.
"""
from __future__ import annotations

import collections
import contextlib
import json
import os
import threading
from pathlib import Path
from typing import Any, Iterator

from parse_bench.inference.providers.parse import kdl_frontier_nano as K

_lock = threading.Lock()
_records: list[dict[str, Any]] = []
_counts: collections.Counter = collections.Counter()
_unmapped: collections.Counter = collections.Counter()


def capture_dir() -> Path | None:
    d = os.environ.get("PARSEBENCH_LABEL_CAPTURE")
    return Path(d) if d else None


def _observe(raw_category: Any, category: str, metadata: dict[str, Any]) -> None:
    raw = str(raw_category)
    in_map = raw in K.NATIVE_LAYOUT_CATEGORY_MAP
    with _lock:
        _counts[(raw, category, in_map)] += 1
        if not in_map:
            _unmapped[raw] += 1
        _records.append(
            {
                "raw_category": raw,
                "category": category,
                "raw_in_map": in_map,
                "parent_raw_category": metadata.get("parent_raw_category"),
            }
        )


@contextlib.contextmanager
def label_capture() -> Iterator[None]:
    """Wrap `_category_for_item` for the duration of a run. Restores on exit."""
    out = capture_dir()
    if out is None:
        yield
        return

    original = K._category_for_item

    def wrapped(item: Any, metadata: dict[str, Any]) -> str:
        category = original(item, metadata)
        try:
            _observe(getattr(item, "raw_category", None), category, metadata or {})
        except Exception:
            pass  # instrumentation must never break a run
        return category

    K._category_for_item = wrapped  # type: ignore[assignment]
    try:
        yield
    finally:
        K._category_for_item = original  # type: ignore[assignment]
        flush()


def flush() -> None:
    """Write the capture. Safe to call more than once."""
    out = capture_dir()
    if out is None:
        return
    out.mkdir(parents=True, exist_ok=True)
    with _lock:
        summary = {
            "total_elements": sum(_counts.values()),
            "distinct_raw_labels": len({k[0] for k in _counts}),
            "unmapped_label_counts": dict(_unmapped.most_common()),
            "unmapped_element_total": sum(_unmapped.values()),
            "by_raw_label": [
                {"raw_category": r, "category": c, "raw_in_map": m, "n": n}
                for (r, c, m), n in _counts.most_common()
            ],
        }
        (out / "label_capture_summary.json").write_text(json.dumps(summary, indent=1))
        (out / "label_capture_records.jsonl").write_text(
            "\n".join(json.dumps(r) for r in _records)
        )


def report() -> str:
    """Human-readable summary, for printing at the end of a run."""
    with _lock:
        total = sum(_counts.values())
        if not total:
            return "label capture: no elements observed"
        lines = [
            f"label capture: {total} elements, "
            f"{len({k[0] for k in _counts})} distinct raw labels, "
            f"{sum(_unmapped.values())} elements carried a label ABSENT from the map"
        ]
        if _unmapped:
            lines.append("  unmapped raw labels (these silently became Text):")
            for raw, n in _unmapped.most_common(15):
                lines.append(f"    {n:>6}  {raw}")
        else:
            lines.append("  every raw label the model emitted is present in the map")
        return "\n".join(lines)

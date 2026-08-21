"""
Regression tests for the two emission defects found by the ParseBench maintainer's
review of PR #99 (2026-08), plus pins on the behavior that must survive the fixes.

The defects (both reproduced before fixing):

1. `bold_run_in_labels` matched its `Label:` regex against the whole line, so a list
   item `- Note: x` became `**- Note:** x` — the bullet swallowed into the bold span,
   which is broken markdown (the list is destroyed). Same for `1. Warning: x`. And
   because the skip test looked at one line at a time, it bolded `Label:` lines INSIDE
   ``` code/LaTeX fences.
2. The relaxed heading gate (`is_titleish_relaxed`, preregistration component (d))
   dropped the vendored terminal-punctuation veto entirely, so an ordinary short
   sentence ending in `.` was promoted to a `# ` heading.

These tests need no network and no model: every function under test is a pure string
(or string+config) transform. They do import the vendored benchmark module, so they run
under the parsebench virtual environment:

    parsebench/.venv/bin/python -m pytest ourparser/tests/
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "parsebench",
        "src",
    ),
)

from ourparser import emission as E  # noqa: E402
from parse_bench.evaluation.metrics.parse.rules_formatting import FormattingRule  # noqa: E402


def _gate(text: str) -> bool:
    """The relaxed gate exactly as `postprocess_markdown` binds it (word_cap=20)."""
    # (max_words=12, caps_ratio=0.60, require_all_caps=False) are the "aggressive"
    # variant parameters the production call passes; max_words is ignored by design.
    return E.is_titleish_relaxed(text, 12, 0.60, False, word_cap=20)


# ---------------------------------------------------------------------------
# Defect 1a — list structure must survive label bolding
# ---------------------------------------------------------------------------

def test_bulleted_label_keeps_bullet_outside_bold_span() -> None:
    # Maintainer's case: was '**- Note:** check the seal' (list destroyed).
    assert E.bold_run_in_labels("- Note: check the seal") == "- **Note:** check the seal"


def test_numbered_label_keeps_number_outside_bold_span() -> None:
    # Maintainer's case: was '**1. Warning:** hot surface'.
    assert E.bold_run_in_labels("1. Warning: hot surface") == "1. **Warning:** hot surface"


def test_paren_numbered_and_star_and_plus_bullets() -> None:
    assert E.bold_run_in_labels("2) Caution: live wire") == "2) **Caution:** live wire"
    assert E.bold_run_in_labels("* Note: x") == "* **Note:** x"
    assert E.bold_run_in_labels("+ Note: x") == "+ **Note:** x"


def test_list_item_without_label_untouched() -> None:
    assert E.bold_run_in_labels("- just a plain item") == "- just a plain item"


def test_emitted_list_form_is_accepted_by_benchmark_bold_matcher() -> None:
    # The variant decision: `- **Note:** x` must earn `is_bold` credit from the real
    # scorer (rules_formatting.py:173-200; the ** arm at :194 searches anywhere in the
    # raw content, so a span inside a list item matches).
    rule = FormattingRule({"type": "is_bold", "text": "Note:", "id": "t"})
    assert rule.run("- **Note:** check the seal", normalized_content="")[0]
    rule2 = FormattingRule({"type": "is_bold", "text": "Warning:", "id": "t"})
    assert rule2.run("1. **Warning:** hot surface", normalized_content="")[0]


# ---------------------------------------------------------------------------
# Defect 1b — fence interiors are never touched
# ---------------------------------------------------------------------------

def test_fenced_latex_interior_untouched() -> None:
    # Maintainer's case: label-shaped lines inside a ``` fence were bolded.
    md = "```latex\n\\alpha: the first coefficient\nE: energy\n```"
    assert E.bold_run_in_labels(md) == md


def test_fenced_code_interior_untouched_tilde_fence() -> None:
    md = "~~~\nkey: value\n~~~"
    assert E.bold_run_in_labels(md) == md


def test_label_after_closed_fence_is_still_bolded() -> None:
    md = "```\nx: 1\n```\n\nAGENCY: Department of Transport"
    want = "```\nx: 1\n```\n\n**AGENCY:** Department of Transport"
    assert E.bold_run_in_labels(md) == want


# ---------------------------------------------------------------------------
# Defect 1 — behavior that must survive the fix
# ---------------------------------------------------------------------------

def test_paragraph_label_still_bolded() -> None:
    # The genuine change (c) case: a run-in label opening a paragraph line.
    assert (
        E.bold_run_in_labels("AGENCY: Department of Transport")
        == "**AGENCY:** Department of Transport"
    )


def test_existing_bold_heading_table_html_untouched() -> None:
    for md in (
        "**already:** bold",
        "# Heading: not a label",
        "| a: | b |",
        "<td>x: y</td>",
        "**Page 3**",
    ):
        assert E.bold_run_in_labels(md) == md


# ---------------------------------------------------------------------------
# Defect 2 — terminal-punctuation veto restored (colon excepted)
# ---------------------------------------------------------------------------

def test_short_sentence_ending_in_period_not_promoted() -> None:
    # Maintainer's case: 'The device was tested.' became '# The device was tested.'
    assert not _gate("The device was tested.")
    md = "para one\n\nThe device was tested.\n\npara two"
    assert E.title_promote(md, lambda t, mw, cr, rac: _gate(t)) == md


def test_sentence_punctuation_vetoed_but_colon_is_not() -> None:
    for bad in ("Ends with bang!", "Ends with question?", "Ends with semi;", "Ends with comma,"):
        assert not _gate(bad)
    # Genuine heading ending in ':' — the reason component (d) exists — still promoted.
    assert _gate("Notes:")
    assert _gate("Scope of Works:")


def test_genuine_notes_heading_still_promoted_end_to_end() -> None:
    md = "para one\n\nNotes:\n\nbody text"
    want = "para one\n\n# Notes:\n\nbody text"
    assert E.title_promote(md, lambda t, mw, cr, rac: _gate(t)) == want


def test_word_cap_20_kept() -> None:
    assert _gate("A Heading Of Exactly Nineteen Words " + "W " * 13)  # 19 words, no punct
    assert not _gate("Word " * 21)  # 21 words


def test_numbered_lines_still_rejected_by_vendored_numlist_veto() -> None:
    # Unchanged by the fix, pinned so nobody mistakes it for one: the vendored
    # numbered-list veto (kept in the relaxed gate) rejects '1. Scope of Works:'.
    assert not _gate("1. Scope of Works:")


# ---------------------------------------------------------------------------
# End-to-end: both fixes through the production postprocess path
# ---------------------------------------------------------------------------

def test_postprocess_markdown_end_to_end() -> None:
    # Paragraphs are multi-line: a standalone one-liner is (by design of change (d))
    # a heading candidate, and a promoted heading is out of bold's scope. A run-in
    # label opens a paragraph that continues, which is what "run-in" means.
    md = (
        "Intro paragraph here\nwith a second line\n\n"
        "The device was tested.\n\n"
        "- Note: check the seal\n\n"
        "```latex\nE: energy\n```\n\n"
        "AGENCY: Department of Transport\nOffice of the Secretary"
    )
    out = E.postprocess_markdown(md, E.GENUINE_ABCD)
    assert "# The device was tested." not in out
    assert "- **Note:** check the seal" in out
    assert "**- Note:**" not in out
    assert "```latex\nE: energy\n```" in out
    assert "**AGENCY:** Department of Transport" in out

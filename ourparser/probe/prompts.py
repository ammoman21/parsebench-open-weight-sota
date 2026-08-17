"""
Formatting-prompt variants for the probe.

WHY THIS EXISTS
The pipeline's entire instruction set is five bare strings at
`kdl_frontier_nano.py:2596-2604`, read by `_nano_payload:2698`. None of them asks
the model for inline formatting. Across 23,802 elements it emits zero bold,
strikethrough, superscript or subscript markers — and 63.3% of scored bold failures
are text merged inline, i.e. unreachable by any post-processing. So the untested
question is simply: does the model produce markup if asked?

DESIGN CONSTRAINTS
1. APPEND, never replace. This is a 1.2B specialist; its trained response is keyed
   to the exact prompt prefix. Every variant keeps `"\nText Recognition:\n"` intact
   and adds after it, so a regression is attributable to the addition alone.
2. Only ask for markers the scorer actually rewards. Verified by executing the
   matchers: bold `**x**` or `<b>` (NOT `<strong>`, NOT `__x__`); strikethrough
   `~~x~~`/`<s>`/`<del>` (NOT single-tilde); `<sup>x</sup>` and `<sub>x</sub>` with
   no inner spaces. `is_underline`, `is_italic` and `is_mark` are annotated but
   belong to NO scored category, so asking for them is pure downside risk.
3. Tags must wrap exactly the styled run, punctuation included — the scorer rejects
   extra words inside the tag for sup/sub/strikethrough.
"""
from __future__ import annotations

BASE_TEXT = "\nText Recognition:\n"

# V0 — control. Byte-identical to the shipped prompt; proves the harness reproduces
# the baseline on this subset before any variant is trusted.
V0_CONTROL = BASE_TEXT

# V1 — minimal. One sentence, no examples. Lowest risk of derailing a small model.
V1_MINIMAL = BASE_TEXT + (
    "Preserve inline formatting from the page: bold as **text**, "
    "strikethrough as ~~text~~, superscript as <sup>text</sup>, "
    "subscript as <sub>text</sub>.\n"
)

# V2 — explicit, with the exact accepted spellings and the wrap rule that the
# scorer enforces. More tokens, more chance of confusing a 1.2B model, but removes
# ambiguity about which marker to emit.
V2_EXPLICIT = BASE_TEXT + (
    "Transcribe the text and preserve inline formatting exactly as it appears:\n"
    "- bold: **text**\n"
    "- strikethrough: ~~text~~\n"
    "- superscript: <sup>text</sup>\n"
    "- subscript: <sub>text</sub>\n"
    "Wrap only the styled characters, including punctuation. Do not add formatting "
    "that is not present on the page. Output nothing else.\n"
)

# V3 — V1 plus the same request on the table stage, since table cells also carry
# scored formatting. Separated so a table-stage regression is attributable.
V3_TEXT_AND_TABLE = V1_MINIMAL

# V4 — the variant the v1/v2 data points at. is_sup rose monotonically with
# instruction strength (0.00 -> 1.01 -> 12.12) while is_bold fell monotonically
# (60.59 -> 58.96 -> 55.24), because bold already earns credit via the heading arm
# of the matcher and over-marking cannibalises it. So request ONLY the sub-types
# that have upside and nothing to lose, and say nothing about bold.
V4_SUPSUB_ONLY = BASE_TEXT + (
    "Mark superscript characters as <sup>text</sup> and subscript characters as "
    "<sub>text</sub>. Do not add any other formatting.\n"
)

VARIANTS: dict[str, dict[str, str]] = {
    "v4_supsub_only": {"text": V4_SUPSUB_ONLY},
    "v0_control":   {"text": V0_CONTROL},
    "v1_minimal":   {"text": V1_MINIMAL},
    "v2_explicit":  {"text": V2_EXPLICIT},
    "v3_text_table": {
        "text": V3_TEXT_AND_TABLE,
        "table": "\nTable Recognition:\n"
                 "Preserve inline formatting inside cells: **bold**, ~~strikethrough~~, "
                 "<sup>superscript</sup>, <sub>subscript</sub>.\n",
    },
}

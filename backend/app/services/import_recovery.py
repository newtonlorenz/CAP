"""Pure checks for reviewer decisions on structured import drafts."""

import re

NUMERIC_REFERENCE = re.compile(r"\d+(?:\.\d+)*")


def correction_error(reference: str | None, parent_reference: str | None,
                     active_references: set[str]) -> str | None:
    if not reference or not NUMERIC_REFERENCE.fullmatch(reference):
        return "Enter a numbered source reference, such as 2.3."
    expected_parent = reference.rpartition(".")[0]
    if parent_reference is not None and parent_reference != expected_parent:
        return f"The immediate parent must be {expected_parent or 'empty for a root reference'}."
    if expected_parent and expected_parent not in active_references:
        return f"Add or correct immediate parent {expected_parent} before resolving this row."
    return None

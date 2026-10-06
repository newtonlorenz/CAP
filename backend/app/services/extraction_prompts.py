"""Provider-neutral extraction instructions and response schema."""

EXTRACTION_PROMPT = """Extract requirements from the supplied source text.

Extract all individual requirements from the following text. For each requirement, return a JSON object with:

- "reference_id": The section/article number (e.g., "4.2.1", "Article 5(a)")
- "title": The section or requirement heading/title if present (e.g., "First certification")
- "text": The full requirement text, verbatim
- "requirement_type": One of "mandatory" (uses shall/must/required), "recommended" (uses should/is recommended), or "informational" (explanatory text, definitions)
- "parent_reference": Parent section number if this is a sub-requirement, null otherwise
- "confidence": Your confidence this is a genuine requirement (0.0 to 1.0)

Rules:
- Only extract actual requirements, not headings, definitions, or preamble unless they contain obligations
- "shall", "must", "is required to" = mandatory
- "should", "is recommended" = recommended
- "may only", "may not", and rows marked [TEST] = mandatory; an unqualified "may" is permission, not a recommendation
- Preserve the exact original text; do not paraphrase
- If a requirement includes a line starting with "Guidance:", "Note:", or "Guideline:", include it as part of the requirement text
- If a section contains multiple distinct obligations, split them into separate requirements
- For tables, extract each row's requirement separately
- Set confidence below 0.7 if you're unsure whether text constitutes a requirement

Document type: {document_type}
Page number: {page_number}

Return ONLY a JSON object with a single key "requirements" whose value is the JSON array. No other text.

Text to analyze:
{text}"""

OPENAI_JSON_SCHEMA = {
    "name": "requirements",
    "schema": {
        "type": "object",
        "properties": {
            "requirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "reference_id": {"type": ["string", "null"]},
                        "title": {"type": ["string", "null"]},
                        "text": {"type": "string"},
                        "requirement_type": {"type": "string"},
                        "parent_reference": {"type": ["string", "null"]},
                        "confidence": {"type": "number"},
                    },
                    "required": [
                        "reference_id",
                        "title",
                        "text",
                        "requirement_type",
                        "parent_reference",
                        "confidence",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["requirements"],
        "additionalProperties": False,
    },
}

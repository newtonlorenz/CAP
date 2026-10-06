"""Optional Jev judgements; never saves templates or sends applicant answers."""

import asyncio
import hashlib

from app.schemas.preparation_quality import FieldSuggestion, ImportEnhancementResponse
from app.services.jev_provider import JevClient, JevConfig, JevError

COLUMNS = ("question", "reference", "section", "type", "options", "required", "help")
TYPES = ("text", "multiline", "yes_no", "date", "number", "choice", "evidence", "uncertain")


def choice(instructions, options):
    return {
        "type": "choice",
        "instructions": instructions,
        "criteria": {key: value for key, value in options.items()},
    }


def selected(answer):
    value = answer.get("choice")
    confidence = min(answer.get("confidence", 0), answer.get("probabilities", {}).get(value, 0))
    return value, confidence


async def enhance_import(body, settings, should_continue=None):
    fingerprint = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    result = ImportEnhancementResponse(status="skipped", input_fingerprint=fingerprint)
    if not settings.jev_enabled or not settings.typesafe_api_key:
        result.warnings = ["Jev is unavailable. The normal import preview remains usable."]
        return result
    if body.settings_revision != settings.jev_settings_revision:
        result.warnings = ["Jev settings changed. Request a fresh preview check."]
        return result
    stale_settings = False

    async def fresh():
        nonlocal stale_settings
        if should_continue is None:
            return True
        try:
            allowed = await should_continue()
        except Exception:
            allowed = False
        if not allowed:
            stale_settings = True
        return allowed

    config = JevConfig.from_settings(settings)
    client = JevClient(config, should_continue=fresh) if should_continue else JevClient(config)

    async def evaluate(state, questions):
        if not await fresh():
            raise JevError("Jev settings changed; preview check stopped.")
        return await client.evaluate(state, questions)

    options = {str(i): header for i, header in enumerate(body.headers)} | {
        "none": "No matching column"
    }
    mapping_questions = {
        key: choice(
            f"Which heading denotes the {key} column of blank form questions? Do not select answers or applicant data.",
            options,
        )
        for key in COLUMNS
    }

    async def run():
        mapped = await evaluate({"headers": body.headers}, mapping_questions)
        result.model = mapped["model"]
        result.usage = dict(mapped.get("usage", {}))
        for key, answer in mapped["answers"].items():
            value, confidence = selected(answer)
            if key in COLUMNS and value != "none" and confidence >= 0.98 and value in options:
                result.suggested_mapping[key] = int(value)
        semaphore = asyncio.Semaphore(2)

        async def batch(rows):
            state = {
                "rows": [
                    {"row_index": row.row_index, "question": row.question, "instructions": row.help}
                    for row in rows
                ]
            }
            questions = {}
            for row in rows:
                path = f"row with row_index {row.row_index}"
                if not row.explicit_type:
                    questions[f"type_{row.row_index}"] = choice(
                        f"Select the supported answer type explicitly requested by {path}. Choose uncertain when wording does not determine a type.",
                        {key: key for key in TYPES},
                    )
                if not row.explicit_required:
                    questions[f"required_{row.row_index}"] = choice(
                        f"Does {path} explicitly require an answer? Preserve conditions; choose uncertain if unspecified.",
                        {
                            "yes": "Explicitly mandatory",
                            "no": "Explicitly optional",
                            "uncertain": "Unspecified or conditional",
                        },
                    )
                nearby = [
                    other
                    for other in rows
                    if other.row_index < row.row_index and row.row_index - other.row_index <= 5
                ]
                if nearby:
                    questions[f"duplicate_{row.row_index}"] = choice(
                        f"Which earlier row asks exactly the same question with the same scope and conditions as {path}? Similar subjects alone are not duplicates.",
                        {str(other.row_index): other.question for other in nearby}
                        | {"none": "No duplicate"},
                    )
            if not questions:
                return
            async with semaphore:
                response = await evaluate(state, questions)
            for key, count in response.get("usage", {}).items():
                result.usage[key] = result.usage.get(key, 0) + count
            for row in rows:
                values = {}
                confidences = []
                for kind in ("type", "required", "duplicate"):
                    answer = response["answers"].get(f"{kind}_{row.row_index}")
                    if not answer:
                        continue
                    value, confidence = selected(answer)
                    if confidence < 0.98 or value == "uncertain":
                        result.warnings.append(
                            f"Row {row.row_index + 1}: {kind} needs review; the normal preview value is retained."
                        )
                        continue
                    if value == "none":
                        continue
                    if kind == "type" and value in TYPES:
                        values["type"] = value
                    elif kind == "required" and value in ("yes", "no"):
                        values["required"] = value == "yes"
                    elif kind == "duplicate" and value in {
                        str(other.row_index)
                        for other in rows
                        if other.row_index < row.row_index and row.row_index - other.row_index <= 5
                    }:
                        values["duplicate_of"] = int(value)
                    else:
                        continue
                    confidences.append(confidence)
                if values:
                    result.field_suggestions.append(
                        FieldSuggestion(
                            row_index=row.row_index, confidence=min(confidences), **values
                        )
                    )

        outcomes = await asyncio.gather(
            *(batch(body.rows[i : i + 10]) for i in range(0, len(body.rows), 10)),
            return_exceptions=True,
        )
        result.status = (
            "partial"
            if any(isinstance(outcome, Exception) for outcome in outcomes)
            else "completed"
        )
        if result.status == "partial":
            result.warnings.append("Some rows could not be checked. Review the normal preview.")

    try:
        await asyncio.wait_for(run(), timeout=30)
    except (JevError, TimeoutError, ValueError, KeyError, TypeError):
        result.status = "partial" if result.model else "skipped"
        result.warnings.append(
            "Jev check incomplete. Review the normal preview; your source wording and manual choices are preserved."
        )
    if not await fresh() or stale_settings:
        result.status = "partial" if result.model else "skipped"
        result.field_suggestions.clear()
        result.suggested_mapping.clear()
        result.warnings = [
            "Jev settings changed. Suggestions were discarded; the normal preview remains usable."
        ]
    result.field_suggestions.sort(key=lambda item: item.row_index)
    return result

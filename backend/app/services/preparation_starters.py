"""Editable workflow examples, never jurisdiction-specific regulatory content."""

from app.schemas.preparation import PreparationField


def question(
    key, label, *, type="text", section="Scope", required=True, reuse_key=None, help_text=None
):
    return PreparationField(
        key=key,
        label=label,
        type=type,
        section=section,
        required=required,
        reuse_key=reuse_key,
        help_text=help_text,
    ).model_dump()


def starter_templates() -> list[dict]:
    applicant = [
        question(
            "legal_name",
            "Legal entity name",
            section="Organisation",
            reuse_key="organisation_legal_name",
        ),
        question(
            "registration",
            "Registration number",
            section="Organisation",
            reuse_key="organisation_registration_number",
            required=False,
        ),
        question(
            "contact",
            "Application contact",
            section="Organisation",
            reuse_key="organisation_application_contact",
        ),
    ]
    examples = [
        (
            "Application preparation",
            "licence_application",
            applicant
            + [
                question("authority", "Receiving authority or body"),
                question("licence", "Licence or permission sought"),
                question("activities", "Activities and locations in scope", type="multiline"),
                question(
                    "application_form",
                    "Official application form or instructions",
                    type="evidence",
                    help_text="Attach the current form or a link to the authority's instructions.",
                ),
                question("support", "Supporting documents", type="evidence"),
            ],
        ),
        (
            "Supplementary annex",
            "licence_application",
            applicant
            + [
                question("annex_reference", "Annex name or reference"),
                question(
                    "instructions",
                    "Current annex form or instructions",
                    type="evidence",
                    help_text="Attach the source form. Add its questions before creating a case.",
                ),
                question("response", "Information requested", type="multiline"),
                question("attachments", "Supporting information", type="evidence", required=False),
            ],
        ),
        (
            "Certification preparation",
            "certification",
            applicant
            + [
                question("standard", "Standard and version"),
                question("system", "Product or system in scope", type="multiline"),
                question("body", "Certification body", required=False),
                question("test_results", "Test results and supporting evidence", type="evidence"),
                question("open_items", "Known gaps and planned actions", type="multiline"),
            ],
        ),
        (
            "Pre-audit preparation",
            "pre_audit",
            [
                question("scope", "Processes and period in scope", type="multiline"),
                question("criteria", "Audit criteria and source documents", type="evidence"),
                question("owner", "Process owner"),
                question("samples", "Sample evidence", type="evidence"),
                question("gaps", "Known gaps and preparation actions", type="multiline"),
            ],
        ),
        (
            "Audit evidence request",
            "audit",
            [
                question("scope", "Audit scope and reference", type="multiline"),
                question("period_start", "Evidence period start", type="date"),
                question("period_end", "Evidence period end", type="date"),
                question("request", "Auditor's request", type="multiline"),
                question("response", "Response to the request", type="multiline"),
                question("records", "Records supporting the response", type="evidence"),
            ],
        ),
        (
            "Evidence collection",
            "evidence_collection",
            [
                question("request", "What needs to be demonstrated?", type="multiline"),
                question("scope", "Entity, system and period covered", type="multiline"),
                question("owner", "Evidence owner"),
                question("records", "Evidence to review", type="evidence"),
                question("limitations", "Coverage limitations", type="multiline", required=False),
            ],
        ),
        (
            "Organisation questionnaire",
            "questionnaire",
            applicant
            + [
                question(
                    "address",
                    "Registered address",
                    type="multiline",
                    section="Organisation",
                    reuse_key="organisation_registered_address",
                ),
                question("services", "Services in scope", type="multiline"),
                question("policy", "Relevant policy or procedure", type="evidence"),
            ],
        ),
    ]
    return [
        {
            "name": name,
            "kind": kind,
            "description": (
                "Illustrative internal checklist. Adapt it to the current authority, "
                "standard or auditor instructions; it is not an official form."
            ),
            "fields": fields,
        }
        for name, kind, fields in examples
    ]

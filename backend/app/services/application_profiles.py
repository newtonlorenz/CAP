"""Proposed market checklists. These are planning aids, never regulator form replicas."""

import json
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.models.application import ApplicationMarketProfile
from app.models.jurisdiction import Jurisdiction
from app.schemas.application import ProfileContent, ProfilePatch

_DK = "https://spillemyndigheden.dk/virksomheder-og-foreninger/spil-der-kraever-en-tilladelse/onlinekasino/soeg-en-tilladelse"
_DK_CERT = "https://www.spillemyndigheden.dk/uploads/2023-10/SCP.02.03.EN_.2.1%20-%20Inspections%20standards%20for%20online%20casino.pdf"
_FI = "https://poliisi.fi/en/applying-for-a-gambling-licence"
_FI_OBLIGATIONS = "https://poliisi.fi/en/licence-holder-s-obligations"
_SE = "https://www.spelinspektionen.se/en/licence-and-permit/Apply-licens-or-permit/"


def _item(key, name, kind, *, source_url, condition=None, repeat_for=None):
    return dict(
        key=key,
        name=name,
        kind=kind,
        required=True,
        source_url=source_url,
        condition=condition,
        repeat_for=repeat_for,
    )


def builtin(code):
    code = code.upper()
    common = {
        "setup_questions": [
            {
                "key": "foreign_applicant",
                "label": "Is the applicant registered abroad?",
                "type": "boolean",
            },
            {
                "key": "representative_used",
                "label": "Will a local representative be used?",
                "type": "boolean",
            },
            {
                "key": "people",
                "label": "People requiring individual declarations",
                "type": "people",
            },
        ],
        "checked_at": "2026-09-30",
        "guidance": [
            "Proposed checklist only. Check authority instructions for completeness.",
            "Blank preparation forms are working documents, not copies of official questions.",
        ],
    }
    if code in {"DK", "DNK"}:
        return {
            **common,
            "guidance": common["guidance"]
            + [
                "Check Danish certification requirements before a licence is issued. "
                "Track the engagement in the certification workspace."
            ],
            "status": "published",
            "label": "Denmark betting and online casino application",
            "authority": "Danish Gambling Authority",
            "source_urls": [_DK, _DK_CERT],
            "items": [
                _item("dk-2-01", "Application form 2-01", "form", source_url=_DK),
                _item(
                    "dk-2-02",
                    "Annex A 2-02 personal declaration",
                    "annex",
                    source_url=_DK,
                    repeat_for="people",
                ),
                _item("dk-2-03", "Annex B 2-03 gambling activities", "annex", source_url=_DK),
                _item(
                    "dk-2-04",
                    "Annex C 2-04 representative",
                    "annex",
                    source_url=_DK,
                    condition="representative_used",
                ),
                _item(
                    "dk-company",
                    "Company registration and ownership documents",
                    "document",
                    source_url=_DK,
                ),
                _item(
                    "dk-financial",
                    "Financial statements and funding documents",
                    "document",
                    source_url=_DK,
                ),
            ],
        }
    if code in {"FI", "FIN"}:
        return {
            **common,
            "setup_questions": [
                common["setup_questions"][0],
                {
                    "key": "foreign_people",
                    "label": "Do any responsible people lack a Finnish personal ID code?",
                    "type": "boolean",
                },
                {
                    "key": "people",
                    "label": "Responsible people without a Finnish personal ID code",
                    "type": "people",
                },
                {
                    "key": "representative_used",
                    "label": "Use a representative? Required when domiciled outside the EEA.",
                    "type": "boolean",
                },
            ],
            "guidance": common["guidance"]
            + [
                "Official fitness certificates must be no older than six months.",
                "Applicants domiciled outside the EEA need a representative.",
                "System audit reports are due before operations begin. Track them in CAP.",
            ],
            "status": "published",
            "label": "Finland gambling licence application",
            "authority": "National Police Board",
            "source_urls": [_FI, _FI_OBLIGATIONS],
            "items": [
                _item("fi-application", "Main application", "form", source_url=_FI),
                _item(
                    "fi-articles",
                    "Articles of association or equivalent",
                    "document",
                    source_url=_FI,
                ),
                _item(
                    "fi-financial", "Financial statements or equivalent", "document", source_url=_FI
                ),
                _item("fi-annual", "Annual report or equivalent", "document", source_url=_FI),
                _item(
                    "fi-foreign-register",
                    "Foreign company register extract",
                    "document",
                    source_url=_FI,
                    condition="foreign_applicant",
                ),
                _item(
                    "fi-foreign-criminal",
                    "Foreign applicant criminal record or equivalent certificate",
                    "document",
                    source_url=_FI,
                    condition="foreign_applicant",
                ),
                _item(
                    "fi-foreign-obligations",
                    "Foreign applicant certificates of fulfilment of obligations",
                    "document",
                    source_url=_FI,
                    condition="foreign_applicant",
                ),
                _item(
                    "fi-person",
                    "Responsible person criminal record and obligations evidence",
                    "document",
                    source_url=_FI,
                    condition="foreign_people",
                    repeat_for="people",
                ),
                _item(
                    "fi-representative",
                    "Representative authorisation",
                    "document",
                    source_url=_FI,
                    condition="representative_used",
                ),
            ],
        }
    return {
        **common,
        "status": "draft",
        "label": "Sweden application planning",
        "authority": "Swedish Gambling Authority",
        "source_urls": [_SE] if code in {"SE", "SWE"} else [],
        "items": [],
        "guidance": [
            "No automated checklist is verified. Define items using current authority guidance."
        ],
    }


async def get_profile(db, jurisdiction_id, user):
    jurisdiction = await db.get(Jurisdiction, jurisdiction_id)
    if jurisdiction is None or not jurisdiction.active:
        raise HTTPException(422, "Jurisdiction is missing or inactive")
    row = await db.scalar(
        select(ApplicationMarketProfile).where(
            ApplicationMarketProfile.organization_id == user.organization_id,
            ApplicationMarketProfile.jurisdiction_id == jurisdiction_id,
        )
    )
    if row:
        return {
            "jurisdiction_id": jurisdiction_id,
            "code": jurisdiction.code,
            "version": row.version,
            "revision": row.revision,
            **json.loads(row.content_json),
        }
    return {
        "jurisdiction_id": jurisdiction_id,
        "code": jurisdiction.code,
        "version": f"builtin-{jurisdiction.code.lower()}-2026-09-30",
        "revision": 0,
        **builtin(jurisdiction.code),
    }


async def patch_profile(db, body: ProfilePatch, user):
    if user.organization_id is None:
        raise HTTPException(422, "An organisation is required to edit market profiles")
    current = await get_profile(db, body.jurisdiction_id, user)
    if current["revision"] != body.expected_revision:
        raise HTTPException(409, "Market profile changed; reload before editing")
    content = ProfileContent.model_validate(
        body.model_dump(exclude={"jurisdiction_id", "expected_revision"})
    )
    keys = [item.key for item in content.items]
    if len(keys) != len(set(keys)):
        raise HTTPException(422, "Profile item keys must be unique")
    revision = body.expected_revision + 1
    version = (
        f"org-{user.organization_id}-{body.jurisdiction_id}-r{revision}-{uuid.uuid4().hex[:8]}"
    )
    values = dict(
        revision=revision,
        version=version,
        content_json=content.model_dump_json(),
        updated_at=datetime.now(UTC),
    )
    if body.expected_revision == 0:
        db.add(
            ApplicationMarketProfile(
                organization_id=user.organization_id, jurisdiction_id=body.jurisdiction_id, **values
            )
        )
    else:
        result = await db.execute(
            update(ApplicationMarketProfile)
            .where(
                ApplicationMarketProfile.organization_id == user.organization_id,
                ApplicationMarketProfile.jurisdiction_id == body.jurisdiction_id,
                ApplicationMarketProfile.revision == body.expected_revision,
            )
            .values(**values)
        )
        if result.rowcount != 1:
            raise HTTPException(409, "Market profile changed; reload before editing")
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "Market profile changed; reload before editing") from exc
    return await get_profile(db, body.jurisdiction_id, user)

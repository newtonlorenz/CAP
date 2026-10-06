"""Denmark SCP.06 v3.1 decision gates; missing attestations stay unresolved.

ATO decisions are recorded attestations, not decisions made by CAP. Working-day
notice uses Danish national holidays; evidence must establish the actual receipt.
"""

import calendar
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.models.change_management import (
    ChangeEntryComponent,
    Component,
    ComponentBaseline,
    ComponentBaselineItem,
)
from app.models.jurisdiction import Jurisdiction
from app.models.requirement import Requirement
from app.models.review import ReviewCycle, ReviewItem


def dt(value):
    if not value:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc)


def months(value, count):
    value = dt(value)
    month = value.month - 1 + count
    year = value.year + month // 12
    month = month % 12 + 1
    return value.replace(
        year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1])
    )


def easter(year):
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    n = h + l - 7 * m + 114
    return date(year, n // 31, n % 31 + 1)


def working_days_after(value, count=5):
    current = dt(value).astimezone(ZoneInfo("Europe/Copenhagen")).date()
    while count:
        current += timedelta(days=1)
        ep = easter(current.year)
        holidays = {
            date(current.year, 1, 1),
            date(current.year, 12, 25),
            date(current.year, 12, 26),
        }
        holidays.update(ep + timedelta(days=x) for x in [-3, -2, 1, 39, 50])
        if current.weekday() < 5 and current not in holidays:
            count -= 1
    return current


def reason(code, message):
    return {"code": code, "message": message}


def programme_readiness(register, now=None):
    now = dt(now) or datetime.now(timezone.utc)
    a = register.programme_assurance or {}
    reasons = []
    for key in (
        "change_plan_reference",
        "change_plan_approved_at",
        "change_plan_approved_by",
        "change_plan_approval_evidence",
        "responsible_owner",
        "ato_accreditation_reference",
        "ato_accreditation_evidence",
        "latest_certification_at",
        "certification_reference",
        "certification_evidence",
        "certification_ato",
    ):
        if not a.get(key):
            reasons.append(
                reason("programme_" + key, "Programme assurance requires " + key.replace("_", " "))
            )
    plan_at = dt(a.get("change_plan_approved_at"))
    if plan_at and plan_at > now:
        reasons.append(
            reason(
                "programme_future_plan", "Senior management plan approval cannot be in the future"
            )
        )
    latest = dt(a.get("latest_certification_at"))
    due = report_due = None
    if latest:
        if latest > now:
            reasons.append(
                reason(
                    "programme_future_certification",
                    "Programme certification cannot be dated in the future",
                )
            )
        due = months(latest, 12)
        explicit = dt(a.get("renewal_due_at"))
        anchor = dt(a.get("cadence_anchor_at"))
        if explicit:
            if explicit > due or explicit <= latest:
                reasons.append(
                    reason(
                        "programme_cadence",
                        "Renewal must preserve the original annual cadence and be within twelve calendar months",
                    )
                )
            else:
                due = explicit
        if anchor:
            anchored_due = anchor
            while anchored_due <= latest:
                anchored_due = months(anchored_due, 12)
            due = min(due, anchored_due)
        report_due = months(latest, 2)
        renewal_report_due = dt(a.get("renewal_report_due_at"))
        if renewal_report_due:
            report_due = min(report_due, renewal_report_due)
        postponed = dt(a.get("postponed_until"))
        if postponed:
            notice = dt(a.get("postponement_notified_at"))
            if (
                postponed > months(due, 2)
                or postponed > months(latest, 14)
                or postponed <= due
                or not notice
                or notice > now
                or notice >= due
                or not a.get("postponement_reference")
            ):
                reasons.append(
                    reason(
                        "programme_postponement",
                        "Postponement requires prior DGA notice and a deadline no later than two months beyond renewal or fourteen months after certification",
                    )
                )
            else:
                due = postponed
                # The postponed renewal report must reach DGA within this same deadline.
        if due < now:
            reasons.append(
                reason("programme_overdue", "Change management programme certification is overdue")
            )
        submitted = dt(a.get("report_submitted_at"))
        if submitted and (submitted < latest or submitted > now or submitted > report_due):
            reasons.append(
                reason(
                    "programme_report_date",
                    "Programme report submission must follow certification and meet the two calendar month deadline",
                )
            )
        if not submitted and report_due < now:
            reasons.append(
                reason(
                    "programme_report_overdue",
                    "Programme certification report submission is overdue or unresolved",
                )
            )
    return {
        "ready": not reasons,
        "reasons": reasons,
        "certification_due_at": due.isoformat() if due else None,
        "report_due_at": report_due.isoformat() if report_due else None,
    }


async def denmark_profile(db, register):
    jurisdiction = await db.get(Jurisdiction, register.jurisdiction_id)
    return bool(jurisdiction and jurisdiction.code.lower() in {"dk", "denmark"})


async def readiness(
    db, change, register, *, now=None, implementation_at=None, implementation_end_at=None
):
    if not await denmark_profile(db, register):
        return None
    now = dt(now) or datetime.now(timezone.utc)
    approval, implementation, verification = [], [], []
    links = list(
        (
            await db.scalars(
                select(ChangeEntryComponent).where(
                    ChangeEntryComponent.change_entry_id == change.id
                )
            )
        ).all()
    )
    snapshots = []
    for link in links:
        component = await db.get(Component, link.component_id)
        snap = (
            link.frozen_snapshot
            if change.status in {"approved", "implemented", "verified", "rolled_back"}
            else None
        )
        if not snap and change.status in {"approved", "implemented", "verified", "rolled_back"}:
            implementation.append(
                reason(
                    "unresolved_approved_scope",
                    "Historical approved component scope has no frozen attestation; reject and reapprove before implementation, or record an evidenced historical scope attestation",
                )
            )
            verification.append(implementation[-1])
        snap = snap or {
            "classification_code": component.classification_code if component else None,
            "regulatory_scope": component.regulatory_scope if component else "unknown",
        }
        snapshots.append((link, snap))
        if snap.get("regulatory_scope", "unknown") == "unknown":
            approval.append(
                reason(
                    "unknown_component_scope", "Resolve regulatory scope for each linked component"
                )
            )
        if not link.planned_version:
            approval.append(
                reason(
                    "planned_component_version", "Record planned version for each linked component"
                )
            )
        if snap.get("classification_code") == 3 and not link.planned_checksum_hash:
            approval.append(
                reason(
                    "planned_component_checksum",
                    "Record planned checksum for each relevance code 3 component",
                )
            )
        if component and link.frozen_snapshot and change.status == "approved":
            # Compare every material snapshot field, not updated_at transport metadata.
            if any(
                getattr(component, k, None) != v
                for k, v in link.frozen_snapshot.items()
                if k not in {"updated_at", "change_owner_id"}
            ):
                implementation.append(
                    reason(
                        "stale_component_baseline",
                        "Component changed since approval; revise and reapprove the proposal",
                    )
                )
    required = [
        "description",
        "complexity_classification",
        "resource_assessment",
        "scheduling_assessment",
        "planned_start_at",
        "planned_end_at",
        "justification",
        "evaluation_effect",
        "evaluation_risk",
        "evaluation_regulatory_impact",
        "evaluation_ciaa_impact",
    ]
    for key in required:
        if not getattr(change, key):
            approval.append(reason("missing_" + key, "Approval requires " + key.replace("_", " ")))
    if not links:
        approval.append(reason("missing_components", "Link at least one component"))
    frozen_scope = (
        change.approved_scope or {}
        if change.status in {"approved", "implemented", "verified", "rolled_back"}
        else {}
    )
    role = frozen_scope.get("responsibility_role", register.responsibility_role)
    if role == "unknown":
        approval.append(
            reason("unknown_responsibility", "Resolve the register's licence responsibility")
        )
    c = change.compliance or {}
    release_compliance = (change.approved_scope or {}).get("implementation_compliance")
    evaluation, cert, defer, regulator, supplier = [
        c.get(k) or {} for k in ["evaluation", "certification", "deferral", "regulator", "supplier"]
    ]
    high = any(s.get("classification_code") == 3 for _, s in snapshots)
    medium = any(
        s.get("classification_code") == 2
        and s.get("regulatory_scope") in {"base_platform", "game_platform", "game"}
        for _, s in snapshots
    )
    pre_cert = any(
        s.get("classification_code") == 3
        and s.get("regulatory_scope") in {"rng", "game", "game_platform"}
        for _, s in snapshots
    )
    if high or medium:
        approved_at = dt(evaluation.get("approved_at"))
        if (
            evaluation.get("status") != "approved"
            or not approved_at
            or approved_at > now
            or not all(evaluation.get(k) for k in ["provider", "reference", "evidence"])
        ):
            approval.append(
                reason(
                    "ato_evaluation",
                    "An evidenced ATO approval of the change evaluation is required; pending or rejected evaluations do not approve a change",
                )
            )
    implementation.extend(approval)
    verification.extend(approval)
    target = dt(implementation_at) or dt(change.implemented_start_at) or now
    certified_at = dt(cert.get("certified_at"))
    certified = (
        cert.get("status") == "certified"
        and certified_at
        and certified_at <= now
        and all(cert.get(k) for k in ["provider", "reference", "evidence"])
    )
    for link, snap in snapshots:
        if snap.get("classification_code") in {2, 3}:
            version = link.implemented_version or link.planned_version
            checksum = link.implemented_checksum_hash or link.planned_checksum_hash
            certified = (
                certified
                and (cert.get("component_versions") or {}).get(str(link.component_id)) == version
            )
            if snap.get("classification_code") == 3:
                certified = (
                    certified
                    and (cert.get("component_checksums") or {}).get(str(link.component_id))
                    == checksum
                )
    due = None
    if pre_cert:
        if not certified or certified_at > target:
            r = reason(
                "preimplementation_certification",
                "Code 3 RNG and game changes need version and checksum bound ATO certification before implementation; postponement is unavailable",
            )
            implementation.append(r)
            verification.append(r)
    elif high:
        due = dt(defer.get("due_at"))
        permission = (release_compliance if release_compliance is not None else c).get(
            "deferral"
        ) or {}
        original_due = dt(permission.get("due_at"))
        if original_due:
            # Later evidence cannot erase or extend the deadline accepted at release.
            due = min(due, original_due) if due else original_due
        qualified = (
            role in {"licensed_operator", "licensed_game_supplier"}
            and all(
                permission.get(k)
                for k in [
                    "permission_reference",
                    "permission_evidence",
                    "qa_function",
                    "qa_qualified",
                    "qa_separate",
                ]
            )
            and due
            and original_due
            and due <= original_due
            and target <= due <= months(target, 3)
            and due >= now
        )
        if not certified and not qualified:
            planned = dt(cert.get("planned_at"))
            end = (
                dt(implementation_end_at)
                or dt(change.implemented_end_at)
                or dt(change.planned_end_at)
            )
            continuation_start = dt(cert.get("continuation_started_at"))
            during = cert.get("timing") == "during" and planned and end and target <= planned <= end
            continuation = (
                cert.get("timing") == "direct_continuation"
                and cert.get("continuation_confirmed") is True
                and cert.get("continuation_evidence")
                and cert.get("provider")
                and continuation_start
                and continuation_start <= now
                and end
                and target <= continuation_start <= end
                and planned
                and planned >= end
            )
            scheduled = bool((during or continuation) and cert.get("schedule_reference"))
            r = reason(
                "code3_certification",
                "Other code 3 changes need certification during or directly after implementation, or evidenced ATO permission for qualified independent QA and a deadline within three calendar months",
            )
            if not scheduled:
                implementation.append(r)
            verification.append(r)
            due = due or planned
        if certified and change.implemented_end_at and certified_at > dt(change.implemented_end_at):
            entitlement = (
                role in {"licensed_operator", "licensed_game_supplier"}
                and all(
                    permission.get(k)
                    for k in [
                        "permission_reference",
                        "permission_evidence",
                        "qa_function",
                        "qa_qualified",
                        "qa_separate",
                    ]
                )
                and original_due
                and original_due <= months(target, 3)
            )
            continuation_start = dt(cert.get("continuation_started_at"))
            continuous = (
                cert.get("timing") == "direct_continuation"
                and cert.get("continuation_confirmed")
                and cert.get("continuation_evidence")
                and cert.get("schedule_reference")
                and continuation_start
                and target <= continuation_start <= dt(change.implemented_end_at)
            )
            if not entitlement and not continuous:
                verification.append(
                    reason(
                        "code3_continuation_unresolved",
                        "Certification after implementation needs evidenced direct continuation or the ATO authorised QA postponement recorded at release",
                    )
                )
        if certified and due and certified_at > due:
            verification.append(
                reason(
                    "code3_certification_late",
                    "Recorded certification completed after the ATO permitted deadline",
                )
            )
    elif medium:
        anchor = dt(c.get("annual_certification_anchor_at"))
        due = dt(c.get("annual_certification_due_at"))
        original_due = dt((release_compliance or {}).get("annual_certification_due_at"))
        if original_due:
            due = min(due, original_due) if due else original_due
        if certified and due and certified_at > due:
            verification.append(
                reason(
                    "annual_certification_late",
                    "Recorded certification completed after its annual deadline",
                )
            )
        bound_schedule = all(
            c.get(k)
            for k in [
                "annual_certification_reference",
                "annual_certification_provider",
                "annual_certification_evidence",
            ]
        )
        if not certified and (
            not bound_schedule
            or not anchor
            or anchor > now
            or not due
            or due < now
            or due > months(anchor, 12)
        ):
            r = reason(
                "annual_certification_schedule",
                "Code 2 requires an evidenced annual certification anchor and an unexpired due date within twelve calendar months",
            )
            implementation.append(r)
            verification.append(r)
    if cert.get("status") == "rejected":
        r = reason("ato_certification_rejected", "ATO certification has been rejected")
        implementation.append(r)
        verification.append(r)
    if any(s.get("regulatory_scope") == "rng" for _, s in snapshots):
        notified = dt(regulator.get("rng_notified_at"))
        if (
            not notified
            or notified > now
            or not regulator.get("rng_reference")
            or working_days_after(notified)
            > target.astimezone(ZoneInfo("Europe/Copenhagen")).date()
        ):
            r = reason(
                "rng_advance_notice",
                "Record DGA RNG notice at least five Danish working days before implementation",
            )
            implementation.append(r)
            verification.append(r)
    if any(s.get("regulatory_scope") in {"game", "game_platform"} for _, s in snapshots):
        if regulator.get("game_approval_required") is None:
            r = reason(
                "game_approval_applicability",
                "Determine and record whether DGA approval is required for this game change",
            )
            implementation.append(r)
            verification.append(r)
        elif regulator.get("game_approval_required"):
            at = dt(regulator.get("game_approval_at"))
            if not regulator.get("game_approval_reference") or not at or at > now or at > target:
                r = reason(
                    "game_prior_approval",
                    "Record applicable DGA game approval before implementation",
                )
                implementation.append(r)
                verification.append(r)
        elif not regulator.get("game_approval_basis"):
            r = reason(
                "game_approval_basis", "Record the basis for game approval being unnecessary"
            )
            implementation.append(r)
            verification.append(r)
    if regulator.get("error_identified_at"):
        at, notified = (
            dt(regulator.get("error_identified_at")),
            dt(regulator.get("error_notified_at")),
        )
        if (
            at > now
            or not notified
            or notified < at
            or notified > now
            or not regulator.get("error_reference")
            or regulator.get("error_notice_immediate") is not True
        ):
            r = reason(
                "instant_error_notice",
                "Record actual DGA receipt and an explicit attestation of immediate error notification; late or unknown notification remains unresolved",
            )
            implementation.append(r)
            verification.append(r)
    if (
        supplier.get("recommended_at")
        and role == "licensed_operator"
        and any(s.get("regulatory_scope") == "base_platform" for _, s in snapshots)
    ):
        if (
            dt(supplier.get("recommended_at")) > target
            or not supplier.get("whole_system_evaluation")
            or not supplier.get("delay_justification")
        ):
            r = reason(
                "supplier_recommendation",
                "Operator must separately assess whole system impact and justify recommendation to implementation delay",
            )
            approval.append(r)
            implementation.append(r)
            verification.append(r)
    ids = frozen_scope.get("blocking_assessment_ids", change.blocking_assessment_ids or [])
    for ident in ids:
        import uuid

        cycle = await db.get(ReviewCycle, uuid.UUID(str(ident)))
        if (
            not cycle
            or cycle.change_entry_id != change.id
            or cycle.organization_id != register.organization_id
        ):
            r = reason(
                "blocking_assessment_scope",
                "Required assessment is unavailable or outside the change scope",
            )
            approval.append(r)
            implementation.append(r)
            verification.append(r)
            continue
        rows = (
            await db.execute(
                select(ReviewItem, Requirement)
                .join(Requirement, Requirement.id == ReviewItem.requirement_id)
                .where(ReviewItem.review_cycle_id == cycle.id)
            )
        ).all()
        unresolved = not rows or any(
            req.requirement_type not in {"informational", "not_applicable"}
            and (
                item.review_status != "confirmed"
                or item.assessment_status not in {"compliant", "not_applicable"}
                or (
                    item.evidence_changed_at
                    and (
                        not item.reviewed_at or dt(item.evidence_changed_at) > dt(item.reviewed_at)
                    )
                )
            )
            for item, req in rows
        )
        if unresolved:
            r = reason(
                "blocking_assessment_unresolved",
                "An explicitly required assessment has unresolved compliance requirements or evidence",
            )
            approval.append(r)
            implementation.append(r)
            verification.append(r)
    if change.integration_related:
        a = register.programme_assurance or {}
        if (
            not c.get("integration_procedure_reference")
            or c.get("integration_procedure_reference") != a.get("integration_procedure_reference")
            or not a.get("integration_procedure_approved_at")
            or dt(a.get("integration_procedure_approved_at")) > now
            or months(a.get("integration_procedure_approved_at"), 12) < now
            or not a.get("integration_procedure_ato")
            or not c.get("integration_requirement_references")
        ):
            verification.append(
                reason(
                    "integration_procedure",
                    "Integration verification requires an ATO approved procedure and related SCP.02/SCP.07 requirements",
                )
            )
        from app.models.change_management import IntegrationCheck

        checks = list(
            (
                await db.scalars(
                    select(IntegrationCheck).where(
                        IntegrationCheck.change_entry_id == change.id,
                        IntegrationCheck.deleted_at.is_(None),
                    )
                )
            ).all()
        )
        if not checks or any(
            x.result != "pass"
            or not x.completed_at
            or dt(x.completed_at) > now
            or (change.implemented_end_at and dt(x.completed_at) < dt(change.implemented_end_at))
            or not x.action_reference
            or not x.evidence_notes
            for x in checks
        ):
            verification.append(
                reason(
                    "integration_checks",
                    "All active integration checks must pass after integration, with actual completion dates, references and evidence",
                )
            )
    candidate_baseline = await db.scalar(
        select(ComponentBaseline)
        .where(
            ComponentBaseline.register_id == register.id,
            ComponentBaseline.certification_scope == "whole_platform",
            ComponentBaseline.certification_at.is_not(None),
            ComponentBaseline.certification_reference.is_not(None),
            ComponentBaseline.certification_evidence.is_not(None),
            ComponentBaseline.certification_ato.is_not(None),
        )
        .order_by(
            ComponentBaseline.certification_at.desc(), ComponentBaseline.established_at.desc()
        )
        .limit(1)
    )
    for link, snapshot in snapshots:
        baseline = (
            await db.get(ComponentBaseline, link.baseline_id)
            if link.baseline_id
            else candidate_baseline
            if change.status in {"draft", "rejected"}
            else None
        )
        if (
            not baseline
            or baseline.certification_scope != "whole_platform"
            or not all(
                [
                    baseline.certification_reference,
                    baseline.certification_at,
                    baseline.certification_evidence,
                    baseline.certification_ato,
                ]
            )
        ):
            implementation.append(
                reason(
                    "certified_platform_baseline",
                    "Bind an evidenced certified whole-platform configuration baseline at approval; manual snapshots do not establish platform certification",
                )
            )
            continue
        if dt(baseline.certification_at) > now or months(baseline.certification_at, 12) < now:
            implementation.append(
                reason(
                    "platform_baseline_renewal",
                    "Certified whole-platform baseline must be renewed during annual recertification",
                )
            )
        item = await db.scalar(
            select(ComponentBaselineItem).where(
                ComponentBaselineItem.baseline_id == baseline.id,
                ComponentBaselineItem.component_id == link.component_id,
            )
        )
        if item is None and not (link.baseline_scope_assessment or "").strip():
            implementation.append(
                reason(
                    "new_component_baseline_scope",
                    "A component absent from the certified baseline needs an explicit scope assessment; the approved change provides its addition lineage",
                )
            )
    assurance = programme_readiness(register, now)
    implementation.extend(assurance["reasons"])
    if change.status != "approved":
        implementation.append(
            reason("implementation_status", "Only approved changes can be implemented")
        )
    if change.status != "implemented":
        verification.append(
            reason("verification_status", "Only implemented changes can be verified")
        )
    if change.status not in {"draft", "rejected"}:
        approval.append(reason("approval_status", "Only draft or rejected changes can be approved"))
    return {
        "rule_profile": "denmark_scp_3.1",
        "approval": {"ready": not approval, "reasons": approval},
        "implementation": {"ready": not implementation, "reasons": implementation},
        "verification": {"ready": not verification, "reasons": verification},
        "certification_due_at": due.isoformat() if due else None,
        "certification_status": (
            "not_required"
            if not (high or medium)
            else (
                "certified"
                if certified
                else "overdue"
                if due and due < now
                else "pending"
                if due
                else "unresolved"
            )
        ),
        "certification_completed": bool(certified),
        "certification_overdue": bool((high or medium) and due and due < now and not certified),
        "release_ready": not implementation,
    }

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "procare-contract-v0.1"
RWS_IR_VERSION = "rws-ir-v0.1"

PROFILE_CONTRACT_FILE = "profile_contract.json"
RWS_IR_FILE = "rws_ir.json"
CONTRACT_VALIDATION_FILE = "contract_validation.json"
EVIDENCE_CERTIFICATES_FILE = "evidence_certificates.json"
CONTRACT_TRACE_FILE = "contract_trace.json"

MAX_SELECTED_TABLES = 12
MAX_FIELDS_PER_ROLE = 40
MAX_CERTIFIED_CLAIMS = 120


def build_profile_contract(excel_info: dict[str, Any]) -> dict[str, Any]:
    """Build a compact profile-grounded evidence contract from excel_info."""

    sheets = list(excel_info.get("sheets") or [])
    columns = _columns_map(excel_info)
    profile = excel_info.get("profile") if isinstance(excel_info.get("profile"), dict) else {}
    tables: list[dict[str, Any]] = []

    for sheet in sheets:
        sheet_profile = (profile.get(sheet) if isinstance(profile, dict) else {}) or {}
        heterogeneous = sheet_profile.get("heterogeneous_profile") if isinstance(sheet_profile, dict) else {}
        heterogeneous = heterogeneous if isinstance(heterogeneous, dict) else {}
        high_structural = heterogeneous.get("high_structural") or {}
        low_structural = heterogeneous.get("low_structural") or {}
        high_knowledge = heterogeneous.get("high_knowledge") or {}
        low_knowledge = heterogeneous.get("low_knowledge") or {}

        legacy_knowledge = sheet_profile.get("knowledge") if isinstance(sheet_profile, dict) else {}
        field_names = [str(c) for c in columns.get(sheet, [])]
        fields = [
            _field_contract(
                sheet=sheet,
                field=field,
                sheet_profile=sheet_profile,
                low_structural=low_structural,
                high_knowledge=high_knowledge,
                low_knowledge=low_knowledge,
                legacy_knowledge=legacy_knowledge,
            )
            for field in field_names
        ]
        candidate_keys = _unique_preserve(
            [str(v) for v in _as_list(high_structural.get("candidate_keys"))]
            + [str(v) for v in _as_list(sheet_profile.get("candidate_keys") if isinstance(sheet_profile, dict) else [])]
            + [field for field in field_names if _looks_like_entity_key(field)]
        )
        temporal_fields = [field for field in field_names if _looks_like_date_field(field)]

        tables.append(
            {
                "name": sheet,
                "row_count": high_structural.get("rows"),
                "column_count": len(field_names),
                "candidate_keys": candidate_keys,
                "temporal_fields": temporal_fields,
                "quality_indicators": high_structural.get("quality_indicators") or {},
                "knowledge_status": {
                    "has_high_knowledge": bool(high_knowledge),
                    "has_low_knowledge": bool(low_knowledge),
                    "ambiguity_flags": heterogeneous.get("ambiguity_flags") or [],
                },
                "fields": fields,
            }
        )

    contract = {
        "version": CONTRACT_VERSION,
        "created_at": _utc_now(),
        "profile_hash": _hash_payload(
            {
                "path": excel_info.get("path"),
                "md5": excel_info.get("md5"),
                "sheets": sheets,
                "columns": columns,
                "profile_keys": sorted(profile.keys()) if isinstance(profile, dict) else [],
            }
        ),
        "source": {
            "path": excel_info.get("path"),
            "md5": excel_info.get("md5"),
            "description": excel_info.get("description"),
        },
        "scope": {
            "sheet_count": len(sheets),
            "field_count": sum(len(columns.get(sheet, [])) for sheet in sheets),
        },
        "tables": tables,
        "contract_clauses": [
            {
                "id": "schema.tables",
                "boundary": "query_to_ir",
                "rule": "RWS-IR may reference only sheets present in this profile contract.",
            },
            {
                "id": "schema.fields",
                "boundary": "query_to_ir",
                "rule": "Variable bindings may reference only fields present in their declared table.",
            },
            {
                "id": "join.keys",
                "boundary": "ir_to_code",
                "rule": "Cross-table joins should use profiled entity or visit keys shared by both tables.",
            },
            {
                "id": "temporal.anchors",
                "boundary": "ir_to_code",
                "rule": "Time-to-event and longitudinal analyses should declare temporal anchor fields.",
            },
            {
                "id": "claims.support",
                "boundary": "artifact_to_claim",
                "rule": "Factual report claims should be linked to validated artifacts, executed code, profile entries, or disclosed assumptions.",
            },
        ],
    }
    return contract


def compile_rws_ir(
    *,
    topic: str | None,
    plan: dict[str, Any],
    excel_info: dict[str, Any],
    profile_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile the current plan/profile into a lightweight RWS-IR."""

    profile_contract = profile_contract or build_profile_contract(excel_info)
    sheets = list(excel_info.get("sheets") or [])
    columns = _columns_map(excel_info)
    selected_tables = _select_tables(plan=plan, excel_info=excel_info)
    plan_text = _as_text(plan)
    goal_text = topic or str(plan.get("topic") or _as_text(plan.get("objective")) or "").strip()

    entity_keys = _infer_entity_keys(selected_tables, columns)
    temporal_anchors = _infer_temporal_anchors(selected_tables, columns, plan_text)
    variable_roles = _infer_variable_roles(selected_tables, columns, plan_text, plan)
    join_graph = _build_join_graph(selected_tables, columns, entity_keys)
    methods = _infer_methods(plan_text)
    required_artifacts = _infer_required_artifacts(plan)

    ir = {
        "version": RWS_IR_VERSION,
        "compiled_at": _utc_now(),
        "profile_contract_ref": PROFILE_CONTRACT_FILE,
        "source_plan_ref": "plan.json",
        "study_goal": goal_text,
        "study_design": _infer_study_design(plan_text),
        "analysis_grain": _infer_analysis_grain(selected_tables, columns, plan_text),
        "tables": [
            {
                "name": sheet,
                "available": sheet in sheets,
                "role": _infer_table_role(sheet, plan_text),
                "field_count": len(columns.get(sheet, [])),
            }
            for sheet in selected_tables
        ],
        "entity_keys": entity_keys,
        "join_graph": join_graph,
        "temporal_anchors": temporal_anchors,
        "variable_roles": variable_roles,
        "methods": methods,
        "required_artifacts": required_artifacts,
        "claim_policy": _default_claim_policy(plan_text),
        "assumptions": _infer_assumptions(plan_text, variable_roles, temporal_anchors),
        "provenance": {
            "profile_hash": profile_contract.get("profile_hash"),
            "selected_table_count": len(selected_tables),
            "source_profile": "excel_info.json",
        },
    }
    ir["static_validation"] = validate_rws_ir(ir=ir, excel_info=excel_info, exec_result=None, job_dir=None)
    return ir


def validate_rws_ir(
    *,
    ir: dict[str, Any],
    excel_info: dict[str, Any],
    exec_result: dict[str, Any] | None = None,
    job_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Validate checkable contract clauses. This is intentionally deterministic and lightweight."""

    columns = _columns_map(excel_info)
    sheets = set(excel_info.get("sheets") or [])
    violations: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    for table in ir.get("tables") or []:
        table_name = str(table.get("name") or "")
        if table_name not in sheets:
            violations.append(
                _violation(
                    "schema.tables",
                    "query_to_ir",
                    "error",
                    f"Referenced table is not present in profile: {table_name}",
                    {"table": table_name},
                    "Select an available sheet or revise the plan target_sheets.",
                )
            )

    for role_name, bindings in (ir.get("variable_roles") or {}).items():
        for binding in _as_list(bindings):
            table_name = str((binding or {}).get("table") or "")
            field_name = str((binding or {}).get("field") or "")
            if not field_name:
                continue
            if table_name not in columns:
                violations.append(
                    _violation(
                        "schema.tables",
                        "query_to_ir",
                        "error",
                        f"Variable role '{role_name}' references missing table: {table_name}",
                        {"table": table_name, "field": field_name, "role": role_name},
                        "Bind this role to an existing table.",
                    )
                )
                continue
            if field_name not in [str(c) for c in columns.get(table_name, [])]:
                violations.append(
                    _violation(
                        "schema.fields",
                        "query_to_ir",
                        "error",
                        f"Variable role '{role_name}' references missing field: {table_name}.{field_name}",
                        {"table": table_name, "field": field_name, "role": role_name},
                        "Bind this role to an existing field or record it as an assumption.",
                    )
                )
            elif role_name in {"exposure", "outcome", "confounder"} and not binding.get("support"):
                warnings.append(
                    _violation(
                        "roles.semantic_support",
                        "query_to_ir",
                        "warning",
                        f"Variable role '{role_name}' has structural support but no explicit semantic validation: {table_name}.{field_name}",
                        {"table": table_name, "field": field_name, "role": role_name},
                        "Confirm the field semantics or add a profile knowledge mapping.",
                    )
                )

    for edge in (ir.get("join_graph") or {}).get("edges") or []:
        left = str(edge.get("left_table") or "")
        right = str(edge.get("right_table") or "")
        keys = [str(k) for k in _as_list(edge.get("keys"))]
        if not keys:
            warnings.append(
                _violation(
                    "join.keys",
                    "ir_to_code",
                    "warning",
                    f"No shared join key declared for {left} -> {right}",
                    {"left_table": left, "right_table": right},
                    "Add a shared entity key or avoid joining these tables.",
                )
            )
            continue
        for key in keys:
            if key not in [str(c) for c in columns.get(left, [])] or key not in [str(c) for c in columns.get(right, [])]:
                violations.append(
                    _violation(
                        "join.keys",
                        "ir_to_code",
                        "error",
                        f"Join key '{key}' is not available on both sides: {left} -> {right}",
                        {"left_table": left, "right_table": right, "key": key},
                        "Use a key shared by both tables.",
                    )
                )

    if _needs_temporal_anchor(_as_text(ir)) and not ir.get("temporal_anchors"):
        warnings.append(
            _violation(
                "temporal.anchors",
                "ir_to_code",
                "warning",
                "The IR appears to describe survival or longitudinal analysis but has no temporal anchors.",
                {},
                "Declare index, event, follow-up, or censoring date fields.",
            )
        )

    runtime_evidence = _validate_runtime_artifacts(exec_result=exec_result, job_dir=job_dir)
    violations.extend(runtime_evidence["violations"])
    warnings.extend(runtime_evidence["warnings"])
    evidence.extend(runtime_evidence["evidence"])

    if exec_result is not None:
        if exec_result.get("success"):
            evidence.append({"type": "execution", "status": "success", "source": "exec_logs.json"})
        else:
            violations.append(
                _violation(
                    "execution.success",
                    "ir_to_code",
                    "error",
                    "Execution result is marked as unsuccessful.",
                    {"source": "exec_logs.json"},
                    "Inspect execution logs and repair generated code or plan assumptions.",
                )
            )

    return {
        "version": CONTRACT_VERSION,
        "validated_at": _utc_now(),
        "ok": not any(v.get("severity") == "error" for v in violations),
        "error_count": sum(1 for v in violations if v.get("severity") == "error"),
        "warning_count": len(warnings),
        "violations": violations,
        "warnings": warnings,
        "evidence": evidence,
    }


def generate_evidence_certificates(
    *,
    report_text: str,
    ir: dict[str, Any],
    validation: dict[str, Any],
    exec_result: dict[str, Any] | None = None,
    job_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Create lightweight claim certificates for report text."""

    claims = _extract_claims(report_text)
    artifact_refs = _artifact_refs(exec_result=exec_result, job_dir=job_dir)
    policy = ir.get("claim_policy") or {}
    allowed_claim_types = set(policy.get("allowed_claim_types") or [])
    certificates = []

    for idx, claim in enumerate(claims[:MAX_CERTIFIED_CLAIMS], start=1):
        claim_type = _classify_claim(claim)
        has_trace = bool(artifact_refs or ir.get("variable_roles") or ir.get("assumptions"))
        policy_ok = (
            claim_type in allowed_claim_types
            or claim_type == "descriptive"
            or (claim_type == "causal" and "causal_with_assumptions" in allowed_claim_types)
        )
        validation_ok = bool(validation.get("ok"))
        status = "admitted" if has_trace and policy_ok and validation_ok else "needs_review"
        notes = []
        if not validation_ok:
            notes.append("Contract validation has unresolved errors.")
        if not policy_ok:
            notes.append(f"Claim type '{claim_type}' is outside the current claim policy.")
        if not has_trace:
            notes.append("No artifact, IR, or assumption trace was available.")

        certificates.append(
            {
                "claim_id": f"q{idx:03d}",
                "claim": claim,
                "claim_type": claim_type,
                "status": status,
                "evidence_certificate": {
                    "artifacts": artifact_refs,
                    "executed_code": _code_ref(exec_result=exec_result, job_dir=job_dir),
                    "ir_fields": _compact_ir_refs(ir),
                    "profile_entries": [ir.get("profile_contract_ref") or PROFILE_CONTRACT_FILE],
                    "assumptions": ir.get("assumptions") or [],
                },
                "checks": {
                    "traceability": has_trace,
                    "policy": policy_ok,
                    "contract_validation": validation_ok,
                },
                "notes": notes,
            }
        )

    return {
        "version": CONTRACT_VERSION,
        "generated_at": _utc_now(),
        "claim_count": len(certificates),
        "admitted_count": sum(1 for c in certificates if c.get("status") == "admitted"),
        "needs_review_count": sum(1 for c in certificates if c.get("status") != "admitted"),
        "certificates": certificates,
    }


def write_contract_bundle(
    *,
    job_dir: str | Path,
    plan: dict[str, Any],
    excel_info: dict[str, Any],
    exec_result: dict[str, Any] | None = None,
    report_text: str | None = None,
) -> dict[str, Any]:
    """Write profile contract, RWS-IR, validation, and optional claim certificates."""

    target = Path(job_dir)
    target.mkdir(parents=True, exist_ok=True)
    profile_contract = build_profile_contract(excel_info)
    topic = str(plan.get("topic") or _as_text(plan.get("objective")) or "")
    rws_ir = compile_rws_ir(topic=topic, plan=plan, excel_info=excel_info, profile_contract=profile_contract)
    validation = validate_rws_ir(ir=rws_ir, excel_info=excel_info, exec_result=exec_result, job_dir=target)
    rws_ir["static_validation"] = validate_rws_ir(ir=rws_ir, excel_info=excel_info, exec_result=None, job_dir=None)

    _write_json(target / PROFILE_CONTRACT_FILE, profile_contract)
    _write_json(target / RWS_IR_FILE, rws_ir)
    _write_json(target / CONTRACT_VALIDATION_FILE, validation)

    certificates = None
    if report_text is None:
        report_path = target / "report.md"
        if report_path.exists():
            report_text = report_path.read_text(encoding="utf-8", errors="replace")
    if report_text:
        certificates = generate_evidence_certificates(
            report_text=report_text,
            ir=rws_ir,
            validation=validation,
            exec_result=exec_result,
            job_dir=target,
        )
        _write_json(target / EVIDENCE_CERTIFICATES_FILE, certificates)

    trace = {
        "version": CONTRACT_VERSION,
        "updated_at": _utc_now(),
        "artifacts": {
            "profile_contract": PROFILE_CONTRACT_FILE,
            "rws_ir": RWS_IR_FILE,
            "contract_validation": CONTRACT_VALIDATION_FILE,
            "evidence_certificates": EVIDENCE_CERTIFICATES_FILE if certificates else None,
        },
        "summary": {
            "contract_ok": validation.get("ok"),
            "error_count": validation.get("error_count"),
            "warning_count": validation.get("warning_count"),
            "claim_count": (certificates or {}).get("claim_count", 0),
            "admitted_claim_count": (certificates or {}).get("admitted_count", 0),
        },
    }
    _write_json(target / CONTRACT_TRACE_FILE, trace)
    return {
        "profile_contract": profile_contract,
        "rws_ir": rws_ir,
        "contract_validation": validation,
        "evidence_certificates": certificates,
        "contract_trace": trace,
    }


def read_contract_bundle(job_dir: str | Path) -> dict[str, Any]:
    target = Path(job_dir)
    bundle = {}
    for key, filename in {
        "profile_contract": PROFILE_CONTRACT_FILE,
        "rws_ir": RWS_IR_FILE,
        "contract_validation": CONTRACT_VALIDATION_FILE,
        "evidence_certificates": EVIDENCE_CERTIFICATES_FILE,
        "contract_trace": CONTRACT_TRACE_FILE,
    }.items():
        path = target / filename
        if path.exists():
            try:
                bundle[key] = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                bundle[key] = None
    return bundle


def _field_contract(
    *,
    sheet: str,
    field: str,
    sheet_profile: dict[str, Any],
    low_structural: dict[str, Any],
    high_knowledge: dict[str, Any],
    low_knowledge: dict[str, Any],
    legacy_knowledge: dict[str, Any],
) -> dict[str, Any]:
    dtypes = low_structural.get("dtypes") or sheet_profile.get("dtypes") or {}
    missing = low_structural.get("missing_rate") or sheet_profile.get("missing_rate") or {}
    unique = low_structural.get("unique_rate") or sheet_profile.get("unique_rate") or {}
    variable_roles = (
        high_knowledge.get("variable_roles")
        or high_knowledge.get("roles")
        or (legacy_knowledge or {}).get("variable_roles")
        or {}
    )
    ontology_mapping = (
        low_knowledge.get("ontology_mapping")
        or low_knowledge.get("ontology")
        or (legacy_knowledge or {}).get("ontology_mapping")
        or {}
    )
    plausibility = (
        low_knowledge.get("plausibility_checks")
        or (legacy_knowledge or {}).get("plausibility")
        or {}
    )
    role = _lookup_mapping(field, variable_roles)
    ontology = _lookup_mapping(field, ontology_mapping)
    validation = _lookup_mapping(field, plausibility)

    support = "semantic" if role or ontology or validation else "structural"
    return {
        "name": field,
        "table": sheet,
        "dtype": dtypes.get(field),
        "missing_rate": missing.get(field),
        "unique_rate": unique.get(field),
        "semantic_role": role,
        "ontology_mapping": ontology,
        "validation_status": validation,
        "support_level": support,
    }


def _select_tables(*, plan: dict[str, Any], excel_info: dict[str, Any]) -> list[str]:
    sheets = [str(s) for s in excel_info.get("sheets") or []]
    required_fields = plan.get("required_fields") if isinstance(plan.get("required_fields"), dict) else {}
    explicit = [str(s) for s in _as_list(plan.get("target_sheets")) if str(s)]
    selected = [s for s in explicit if s in sheets]
    for sheet in required_fields.keys():
        if sheet in sheets and sheet not in selected:
            selected.append(sheet)

    plan_text = _as_text(plan).casefold()
    for sheet in sheets:
        if sheet.casefold() in plan_text and sheet not in selected:
            selected.append(sheet)

    if not selected:
        priority_terms = ("dm", "baseline", "outcome", "follow", "visit", "treatment", "survival", "人口", "基线", "随访", "治疗", "结局")
        for sheet in sheets:
            if any(term in sheet.casefold() for term in priority_terms):
                selected.append(sheet)
            if len(selected) >= MAX_SELECTED_TABLES:
                break

    if not selected:
        selected = sheets[:MAX_SELECTED_TABLES]
    return selected[:MAX_SELECTED_TABLES]


def _infer_variable_roles(
    selected_tables: list[str],
    columns: dict[str, list[str]],
    plan_text: str,
    plan: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    roles: dict[str, list[dict[str, Any]]] = {
        "identifier": [],
        "exposure": [],
        "outcome": [],
        "censoring": [],
        "confounder": [],
        "analysis_variable": [],
    }
    required_fields = plan.get("required_fields") if isinstance(plan.get("required_fields"), dict) else {}
    objective = plan.get("objective") if isinstance(plan.get("objective"), dict) else {}
    core_variables = objective.get("core_variables") if isinstance(objective.get("core_variables"), dict) else {}
    role_text = {role: _as_text(value) for role, value in (core_variables or {}).items()}

    for table in selected_tables:
        for field in columns.get(table, []):
            field = str(field)
            role = _classify_field_role(field, plan_text, role_text)
            if role and len(roles[role]) < MAX_FIELDS_PER_ROLE:
                roles[role].append(_binding(table, field, role, support="name_heuristic"))

    for table, fields in required_fields.items():
        if table not in columns:
            continue
        for field in _as_list(fields):
            field = str(field)
            if field not in columns.get(table, []):
                roles["analysis_variable"].append(_binding(str(table), field, "analysis_variable", support=None))
                continue
            role = _classify_field_role(field, plan_text, role_text) or "analysis_variable"
            if not _has_binding(roles[role], str(table), field):
                roles[role].append(_binding(str(table), field, role, support="plan_required_field"))

    return {role: bindings for role, bindings in roles.items() if bindings}


def _infer_temporal_anchors(selected_tables: list[str], columns: dict[str, list[str]], plan_text: str) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    for table in selected_tables:
        for field in columns.get(table, []):
            field = str(field)
            if not _looks_like_date_field(field):
                continue
            role = "time"
            text = field.casefold()
            if any(term in text for term in ("sgdat", "surgery", "index", "baseline", "手术", "基线")):
                role = "index_date"
            elif any(term in text for term in ("death", "dedat", "event", "复发", "死亡", "pad")):
                role = "event_date"
            elif any(term in text for term in ("follow", "visit", "随访", "vt")):
                role = "follow_up"
            elif any(term in text for term in ("end", "censor", "末次", "截止")):
                role = "censoring_date"
            anchors.append({"table": table, "field": field, "role": role, "support": "name_heuristic"})
    if not _needs_temporal_anchor(plan_text):
        return anchors[:20]
    return anchors[:40]


def _infer_entity_keys(selected_tables: list[str], columns: dict[str, list[str]]) -> list[dict[str, Any]]:
    keys: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for table in selected_tables:
        for field in columns.get(table, []):
            field = str(field)
            if not _looks_like_entity_key(field):
                continue
            item = (table, field)
            if item in seen:
                continue
            seen.add(item)
            role = "visit_key" if "visit" in field.casefold() or "访视" in field else "subject_key"
            keys.append({"table": table, "field": field, "role": role, "support": "name_heuristic"})
    return keys[:60]


def _build_join_graph(
    selected_tables: list[str],
    columns: dict[str, list[str]],
    entity_keys: list[dict[str, Any]],
) -> dict[str, Any]:
    common_key_names = _unique_preserve([str(k.get("field")) for k in entity_keys if k.get("field")])
    edges = []
    for idx, left in enumerate(selected_tables):
        left_cols = set(str(c) for c in columns.get(left, []))
        for right in selected_tables[idx + 1 :]:
            right_cols = set(str(c) for c in columns.get(right, []))
            shared = [key for key in common_key_names if key in left_cols and key in right_cols]
            if shared:
                edges.append({"left_table": left, "right_table": right, "keys": shared[:3], "join_type": "profile_key"})
            if len(edges) >= 80:
                break
        if len(edges) >= 80:
            break
    return {"keys": common_key_names, "edges": edges}


def _infer_study_design(plan_text: str) -> dict[str, Any]:
    lower = plan_text.casefold()
    design_type = "descriptive"
    if any(term in lower for term in ("cohort", "队列", "随访", "survival", "生存", "cox", "kaplan", "km")):
        design_type = "observational_cohort"
    elif any(term in lower for term in ("case-control", "病例对照")):
        design_type = "case_control"
    elif any(term in lower for term in ("cross-sectional", "横断面")):
        design_type = "cross_sectional"
    return {
        "type": design_type,
        "reporting_standard": "STROBE/RECORD-style transparent reporting",
        "support": "inferred_from_plan",
    }


def _infer_analysis_grain(selected_tables: list[str], columns: dict[str, list[str]], plan_text: str) -> dict[str, Any]:
    lower = plan_text.casefold()
    if "visit" in lower or "访视" in lower or "longitudinal" in lower:
        grain = "visit-level or longitudinal"
    else:
        grain = "subject-level"
    keys = []
    for table in selected_tables:
        for field in columns.get(table, []):
            if _looks_like_entity_key(str(field)):
                keys.append({"table": table, "field": str(field)})
    return {"grain": grain, "keys": keys[:20], "support": "inferred_from_profile_keys"}


def _infer_methods(plan_text: str) -> list[dict[str, Any]]:
    lower = plan_text.casefold()
    candidates = [
        ("descriptive_statistics", ("describe", "summary", "描述", "统计")),
        ("group_comparison", ("chi-square", "fisher", "t-test", "rank", "组间", "比较", "smd")),
        ("kaplan_meier", ("kaplan", "k-m", "km", "log-rank", "生存曲线")),
        ("cox_regression", ("cox", "hazard", "hr", "风险比")),
        ("propensity_score", ("propensity", "iptw", "matching", "倾向")),
        ("missingness_analysis", ("missing", "缺失")),
    ]
    methods = []
    for method, terms in candidates:
        if any(term in lower for term in terms):
            methods.append({"name": method, "support": "inferred_from_plan"})
    if not methods:
        methods.append({"name": "descriptive_statistics", "support": "default"})
    return methods


def _infer_required_artifacts(plan: dict[str, Any]) -> dict[str, Any]:
    artifacts = plan.get("artifacts") if isinstance(plan.get("artifacts"), dict) else {}
    figures = _as_list(artifacts.get("figures"))
    tables = _as_list(artifacts.get("tables"))
    return {
        "report": artifacts.get("report") or "report.md",
        "plots_dir": artifacts.get("plots") or "plots/",
        "figure_manifest": "plots/figure_manifest.json",
        "figures": figures,
        "tables": tables,
        "execution_log": "exec_logs.json",
    }


def _default_claim_policy(plan_text: str) -> dict[str, Any]:
    lower = plan_text.casefold()
    allowed = ["descriptive", "comparison", "association", "limitation"]
    if any(term in lower for term in ("causal", "因果", "target trial", "倾向评分", "iptw", "matching")):
        allowed.append("causal_with_assumptions")
    return {
        "allowed_claim_types": allowed,
        "blocked_without_assumption": ["causal", "safety-critical", "treatment-recommendation"],
        "wording_rules": [
            "Use descriptive or association wording unless design assumptions are explicit.",
            "Do not claim clinical efficacy or safety beyond executed artifacts and recorded assumptions.",
            "Mention proxy variables, sparse endpoints, and missing temporal anchors as limitations.",
        ],
    }


def _infer_assumptions(
    plan_text: str,
    variable_roles: dict[str, list[dict[str, Any]]],
    temporal_anchors: list[dict[str, Any]],
) -> list[str]:
    assumptions = [
        "This lightweight RWS-IR is compiled from the current plan and profile artifacts; it is an implementation-facing contract, not a clinical protocol approval.",
        "Fields with name-heuristic support require human or ontology confirmation before high-stakes interpretation.",
    ]
    if not variable_roles.get("outcome"):
        assumptions.append("No explicit outcome field was bound; report claims should remain descriptive until outcome mapping is confirmed.")
    if _needs_temporal_anchor(plan_text) and not temporal_anchors:
        assumptions.append("Survival or longitudinal wording was detected but no temporal anchor was available in the compiled IR.")
    return assumptions


def _validate_runtime_artifacts(
    *,
    exec_result: dict[str, Any] | None,
    job_dir: str | Path | None,
) -> dict[str, list[dict[str, Any]]]:
    violations: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    if job_dir is None:
        return {"violations": violations, "warnings": warnings, "evidence": evidence}

    target = Path(job_dir)
    script_path = None
    if exec_result:
        raw_code_path = exec_result.get("code_path")
        if raw_code_path:
            script_path = Path(str(raw_code_path))
    if script_path is None or not script_path.exists():
        for name in ("analysis.py", "main.py"):
            candidate = target / name
            if candidate.exists():
                script_path = candidate
                break
    if script_path and script_path.exists():
        evidence.append({"type": "code", "path": _rel_or_name(script_path, target), "status": "exists"})
    elif exec_result is not None:
        violations.append(
            _violation(
                "artifacts.code",
                "ir_to_code",
                "error",
                "No generated analysis script was found.",
                {"expected": ["analysis.py", "main.py"]},
                "Generate or restore the executable entry point.",
            )
        )

    manifest = target / "plots" / "figure_manifest.json"
    if manifest.exists():
        evidence.append({"type": "figure_manifest", "path": "plots/figure_manifest.json", "status": "exists"})
        try:
            manifest_items = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(manifest_items, list):
                evidence.append({"type": "figure_count", "count": len(manifest_items), "source": "plots/figure_manifest.json"})
        except Exception as exc:
            warnings.append(
                _violation(
                    "artifacts.figure_manifest",
                    "ir_to_code",
                    "warning",
                    f"Figure manifest exists but could not be parsed: {exc}",
                    {"path": "plots/figure_manifest.json"},
                    "Rewrite a valid JSON figure manifest.",
                )
            )
    elif exec_result is not None:
        warnings.append(
            _violation(
                "artifacts.figure_manifest",
                "ir_to_code",
                "warning",
                "plots/figure_manifest.json was not found.",
                {"expected": "plots/figure_manifest.json"},
                "Emit a figure manifest for publication figures.",
            )
        )

    report = target / "report.md"
    if report.exists():
        evidence.append({"type": "report", "path": "report.md", "status": "exists"})
    return {"violations": violations, "warnings": warnings, "evidence": evidence}


def _extract_claims(report_text: str) -> list[str]:
    claims: list[str] = []
    in_code = False
    for raw_line in report_text.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line:
            continue
        if line.startswith("#") or line.startswith("!") or line.startswith("|"):
            continue
        line = re.sub(r"^\s*[-*+]\s+", "", line)
        line = re.sub(r"^\s*\d+[.)]\s+", "", line)
        if len(line) < 12:
            continue
        pieces = re.split(r"(?<=[。！？.!?])\s+", line)
        for piece in pieces:
            piece = piece.strip()
            if 12 <= len(piece) <= 500:
                claims.append(piece)
            elif len(piece) > 500:
                claims.append(piece[:500])
        if len(claims) >= MAX_CERTIFIED_CLAIMS:
            break
    return claims


def _classify_claim(claim: str) -> str:
    lower = claim.casefold()
    if any(term in lower for term in ("cause", "causal", "导致", "使得", "因果")):
        return "causal"
    if any(term in lower for term in ("hazard", "risk", "associated", "关联", "相关", "hr", "or")):
        return "association"
    if any(term in lower for term in ("higher", "lower", "different", "compare", "差异", "高于", "低于", "比较")):
        return "comparison"
    if any(term in lower for term in ("limitation", "assumption", "缺失", "限制", "假设")):
        return "limitation"
    return "descriptive"


def _artifact_refs(*, exec_result: dict[str, Any] | None, job_dir: str | Path | None) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if exec_result:
        refs.append({"type": "execution_log", "path": "exec_logs.json"})
        plots = exec_result.get("plots") or []
        for plot in _as_list(plots)[:20]:
            refs.append({"type": "plot", "path": f"plots/{plot}"})
    if job_dir is not None:
        target = Path(job_dir)
        manifest = target / "plots" / "figure_manifest.json"
        if manifest.exists():
            refs.append({"type": "figure_manifest", "path": "plots/figure_manifest.json"})
        report = target / "report.md"
        if report.exists():
            refs.append({"type": "report", "path": "report.md"})
    return refs


def _code_ref(*, exec_result: dict[str, Any] | None, job_dir: str | Path | None) -> dict[str, Any] | None:
    if exec_result and exec_result.get("code_path"):
        path = Path(str(exec_result.get("code_path")))
        if job_dir is not None:
            return {"path": _rel_or_name(path, Path(job_dir))}
        return {"path": str(path)}
    if job_dir is not None:
        target = Path(job_dir)
        for name in ("analysis.py", "main.py"):
            if (target / name).exists():
                return {"path": name}
    return None


def _compact_ir_refs(ir: dict[str, Any]) -> dict[str, Any]:
    return {
        "study_goal": ir.get("study_goal"),
        "study_design": ir.get("study_design"),
        "analysis_grain": ir.get("analysis_grain"),
        "variable_roles": ir.get("variable_roles"),
        "methods": ir.get("methods"),
        "claim_policy": ir.get("claim_policy"),
    }


def _classify_field_role(field: str, plan_text: str, role_text: dict[str, str]) -> str | None:
    text = field.casefold()
    if _looks_like_entity_key(field):
        return "identifier"
    if any(term in text for term in ("death", "dead", "dedat", "surv", "recurr", "event", "os", "rfs", "死亡", "复发", "生存", "结局")):
        return "outcome"
    if any(term in text for term in ("censor", "last", "末次", "删失")):
        return "censoring"
    if any(term in text for term in ("treat", "therapy", "drug", "dose", "tace", "imu", "tart", "thet", "radi", "loab", "cmed", "治疗", "用药", "方案")):
        return "exposure"
    if any(term in text for term in ("age", "sex", "gender", "bclc", "child", "ecog", "afp", "height", "weight", "年龄", "性别", "分期")):
        return "confounder"
    for role, text_blob in role_text.items():
        if field in text_blob:
            if role in {"exposure", "outcome", "covariates", "confounder", "confounders"}:
                return "confounder" if role in {"covariates", "confounders"} else role
    if field and field.casefold() in plan_text.casefold():
        return "analysis_variable"
    return None


def _infer_table_role(sheet: str, plan_text: str) -> str:
    lower = sheet.casefold()
    if any(term in lower for term in ("dm", "baseline", "人口", "基线")):
        return "baseline"
    if any(term in lower for term in ("visit", "vt", "follow", "随访")):
        return "follow_up"
    if any(term in lower for term in ("treat", "tace", "imu", "tart", "thet", "radi", "loab", "cmed", "治疗")):
        return "exposure"
    if any(term in lower for term in ("ae", "sae", "event", "outcome", "结局", "不良")):
        return "outcome"
    if sheet in plan_text:
        return "plan_referenced"
    return "supporting"


def _binding(table: str, field: str, role: str, support: str | None) -> dict[str, Any]:
    return {"table": table, "field": field, "role": role, "support": support}


def _has_binding(bindings: list[dict[str, Any]], table: str, field: str) -> bool:
    return any(str(item.get("table")) == table and str(item.get("field")) == field for item in bindings)


def _lookup_mapping(field: str, mapping: Any) -> Any:
    if not isinstance(mapping, dict):
        return None
    if field in mapping:
        return mapping.get(field)
    for key, value in mapping.items():
        if isinstance(value, str) and value == field:
            return key
        if isinstance(value, list) and field in [str(v) for v in value]:
            return key
        if isinstance(value, dict):
            nested = _lookup_mapping(field, value)
            if nested:
                return nested
    return None


def _columns_map(excel_info: dict[str, Any]) -> dict[str, list[str]]:
    columns = excel_info.get("columns")
    if isinstance(columns, dict):
        return {str(k): [str(v) for v in _as_list(vals)] for k, vals in columns.items()}
    return {}


def _looks_like_entity_key(field: str) -> bool:
    lower = field.casefold()
    key_terms = ("subject_id", "patient_id", "subjid", "subj", "patient", "visit_no", "record_id", "受试者", "患者", "访视")
    if lower in {"id", "subjectid", "patientid"}:
        return True
    return any(term in lower for term in key_terms)


def _looks_like_date_field(field: str) -> bool:
    lower = field.casefold()
    return any(term in lower for term in ("date", "dat", "time", "day", "日期", "时间"))


def _needs_temporal_anchor(text: str) -> bool:
    lower = text.casefold()
    return any(term in lower for term in ("survival", "follow-up", "follow up", "longitudinal", "kaplan", "cox", "os", "rfs", "生存", "随访", "复发", "死亡"))


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            parts.append(str(key))
            parts.append(_as_text(item))
        return " ".join(parts)
    if isinstance(value, list):
        return " ".join(_as_text(item) for item in value)
    return str(value)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return [value]


def _unique_preserve(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _violation(
    clause: str,
    boundary: str,
    severity: str,
    message: str,
    location: dict[str, Any],
    repair_action: str,
) -> dict[str, Any]:
    digest = hashlib.sha1(f"{clause}|{boundary}|{message}|{json.dumps(location, ensure_ascii=False, default=str)}".encode("utf-8")).hexdigest()[:10]
    return {
        "id": f"u_{digest}",
        "clause": clause,
        "boundary": boundary,
        "severity": severity,
        "message": message,
        "location": location,
        "repair_action": repair_action,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _hash_payload(payload: Any) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:24]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _rel_or_name(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve())).replace("\\", "/")
    except Exception:
        return path.name

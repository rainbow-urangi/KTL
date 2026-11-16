"""GT-independent deterministic serialization of persisted canonical process maps.
No model execution, identity pairing, raw labels or evaluation contracts are accepted.
"""
import json

VERSION = "business-process-serializer-3"
RULES = {
    "page_entry": ("SCREEN_ENTRY", "BPS-01"),
    "input": ("INPUT", "BPS-02"),
    "selection": ("SELECT", "BPS-03"),
    "detail_open": ("DETAIL_OPEN", "BPS-04"),
    "detail_close": ("DETAIL_CLOSE", "BPS-05"),
    "submit_save": ("SUBMIT_SAVE", "BPS-06"),
}

def serialize(models, nodes, occurrences):
    """Typed UI occurrences become steps; HTTP occurrences remain unlinked evidence.

    Graph nodes outside canonical sequences are retained in graph_evidence, never
    silently selected as substitute procedures. Repeated sequence nodes stay repeated.
    """
    by_node = {n["node_id"]: n for n in nodes}
    if len(by_node) != len(nodes):
        raise ValueError("Duplicate node ID")
    ids = [m["process_model_id"] for m in models]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate process ID")
    by_occurrence = {}
    for occurrence in occurrences:
        key = (occurrence["process_instance_id"], occurrence["step_order"])
        if key in by_occurrence:
            raise ValueError("Ambiguous occurrence identity")
        by_occurrence[key] = occurrence
    processes = []
    for model in models:
        pid = model["process_model_id"]
        steps = []
        technical_evidence = []
        for order, nid in enumerate(model["canonical_node_sequence"], 1):
            if nid not in by_node or by_node[nid]["process_model_id"] != pid:
                raise ValueError("Broken canonical node reference")
            node = by_node[nid]
            key = (model["canonical_instance_id"], order)
            if key not in by_occurrence:
                raise ValueError("Missing canonical occurrence")
            occurrence = by_occurrence[key]
            if occurrence["node_id"] != nid or occurrence["process_model_id"] != pid:
                raise ValueError("Mismatched canonical occurrence")
            for field in ("action", "http_method", "normalized_endpoint", "page_path", "target_role"):
                if occurrence.get(field, "") != node.get(field, ""):
                    raise ValueError("Occurrence semantic fields differ from graph")
            event_ids = occurrence.get("source_event_evidence")
            if not isinstance(event_ids, list) or not event_ids or any(not isinstance(e, str) or not e for e in event_ids) or len(set(event_ids)) != len(event_ids):
                raise ValueError("Invalid occurrence event evidence")
            action = node.get("action", "")
            method = node.get("http_method", "").upper()
            category, rule = RULES.get(action, ("UNRESOLVED", "BPS-09"))
            if action in ("api_confirmation", "api_failure"):
                category = "HTTP_READ" if method in ("GET", "HEAD", "OPTIONS") else (
                    "HTTP_WRITE" if method in ("POST", "PUT", "PATCH", "DELETE") else "HTTP_UNKNOWN")
                rule = "BPS-07" if action == "api_confirmation" else "BPS-08"
            evidence = json.loads(json.dumps(node, ensure_ascii=False))
            record = {"generated_step_id": f"{pid}-B{len(steps)+1:03d}",
                "step_order": len(steps)+1, "action_type": category,
                "menu_page": node.get("page_path", ""), "target": node.get("target_role", ""),
                "http_method": method, "endpoint": node.get("normalized_endpoint", ""),
                "source_event_ids": list(event_ids),
                "source_instance_id": occurrence["process_instance_id"],
                "source_occurrence_order": occurrence["step_order"],
                "occurrence_evidence": json.loads(json.dumps(occurrence, ensure_ascii=False)),
                "graph_node_evidence": evidence,
                "semantic_status": "UNRESOLVED_TECHNICAL_EVIDENCE" if action in ("api_confirmation", "api_failure") else "DIRECT_TYPED_MODEL_ACTION",
                "source_node_ids": [nid], "evidence": [json.loads(json.dumps(occurrence, ensure_ascii=False))],
                "serializer_rule_id": rule, "source_action": action,
                "semantic_limit": "HTTP success does not prove business completion" if action == "api_confirmation" else "Direct typed model output only"}
            if action in ("api_confirmation", "api_failure"):
                # No causal inference from adjacency, success or a recent-action hint.
                record.pop("generated_step_id")
                record.pop("step_order")
                record["technical_evidence_id"] = f"{pid}-T{order:03d}"
                record["linked_generated_step_id"] = None
                record["relationship_status"] = "UNLINKED_NO_VERIFIED_CAUSAL_IDENTITY"
                technical_evidence.append(record)
            else:
                steps.append(record)
        processes.append({"source_process_id": pid,
            "canonical_instance_id": model["canonical_instance_id"], "business_steps": steps,
            "unlinked_technical_evidence": technical_evidence})
    return {"serializer_version": VERSION, "processes": processes,
        "generated_business_step_count": sum(len(p["business_steps"]) for p in processes),
        "denominator_policy": "ALL business_steps across ALL processes; no filtering",
        "graph_evidence": json.loads(json.dumps(nodes, ensure_ascii=False)),
        "source_occurrence_evidence": json.loads(json.dumps(occurrences, ensure_ascii=False)),
        "technical_evidence_count": sum(len(p["unlinked_technical_evidence"]) for p in processes),
        "auxiliary_exclusions": [], "merge_policy": "NONE_WITHOUT_VERIFIED_CAUSAL_LINK",
        "semantic_readiness": "READY_FOR_INDEPENDENT_VERIFICATION",
        "input_occurrence_count": sum(len(m["canonical_node_sequence"]) for m in models)}

def canonical_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()

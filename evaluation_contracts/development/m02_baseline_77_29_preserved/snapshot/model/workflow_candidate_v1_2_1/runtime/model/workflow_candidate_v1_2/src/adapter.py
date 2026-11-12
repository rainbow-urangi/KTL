"""Canonical procedures retain read/write identity; external product APIs are untouched."""

def canonical_for_generator(tables,process_model_id):
    model=next(p for p in tables['process_models'] if p['process_model_id']==process_model_id)
    steps=[s for s in tables['process_steps'] if s['process_instance_id']==model['canonical_instance_id']]
    return dict(schema_version='workflow-canonical-1.1',process_model_id=process_model_id,
                procedures=[dict(id=s['node_id'],order=s['step_order'],action=s['action'],http_method=s['http_method'],
                                 target=dict(page_path=s['page_path'],role=s['target_role'],normalized_endpoint=s['normalized_endpoint']),
                                 evidence=s['source_event_evidence']) for s in steps])

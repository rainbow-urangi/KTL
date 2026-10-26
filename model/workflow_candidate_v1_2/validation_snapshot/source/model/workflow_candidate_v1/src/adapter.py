"""모델과 외부 생성기를 분리하는 canonical evidence adapter; API 변경 없음."""

def canonical_for_generator(tables, process_model_id):
    model=next(p for p in tables['process_models'] if p['process_model_id']==process_model_id)
    steps=[s for s in tables['process_steps'] if s['process_instance_id']==model['canonical_instance_id']]
    return {'schema_version':'workflow-canonical-1','process_model_id':process_model_id,
            'procedures':[{'id':s['node_id'],'order':s['step_order'],'action':s['action'],
                           'target':{'page_path':s['page_path'],'role':s['target_role']},
                           'evidence':s['source_event_evidence']} for s in steps]}

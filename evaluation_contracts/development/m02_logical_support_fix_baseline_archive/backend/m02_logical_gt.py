"""GT-only evaluation sidecar compiler. No generated/model/raw/result input or IO."""
import copy
CONTRACT = 'LOGICAL_BUSINESS_PROCEDURE_V1'
RULES = {
    'contract':CONTRACT,'version':'gt-logical-role-1',
    'context':'Original TD-04 menu_screen_name is logical business context, not mandatory physical DOM/path equality.',
    'entry':'First named context => ENTER_CONTEXT; direct final PAGE_ENTER/MENU_ENTER plus declared logical name.',
    'registration':'Pre-input 등록 => INITIATE_REGISTRATION; post-input 등록 => COMMIT_REGISTRATION. Runtime phase is derived from final actions/order only.',
    'input':'INPUT_INFORMATION requires one final INPUT procedure explicitly asserting the whole named information object. A narrower field or union of multiple steps cannot substitute.',
    'save':'Direct SAVE with source target and logical context, not HTTP success.',
    'inspection':'Direct RESULT_CHECK of source completion intent after a write; CONFIRM/passive message not substitutes.',
    'end':'Explicit final SELECT/CONFIRM of source end command plus logical context is sufficient. Last position/POPUP_CLOSE alone is not. Without direct proof or authoritative end definition, unmatched end is incomparable, never zero.',
    'targets':'Source labels/aliases conserved. Only symmetric action suffix grammar for selection/input objects; no new aliases or business dictionaries.',
    'physical':'Only if authoritatively declared; missing physical bindings are not FINAL blockers.',
    'unknown':'No action/context wildcard. Missing potentially relevant semantic context/phase yields incomparable, not fabricated zero.',
    'alignment':'Same process/execution, order-preserving one-to-one; no merge/drop/regeneration; every scoped generated step remains denominator.'}

def compile_roles(truth):
    """Reads procedure source words/order and logical menus only; arbitrary BU IDs."""
    processes=[];unresolved=[];conditional=[]
    for process in truth['processes']:
        source_steps=process['procedures'];rows=[]
        for index,step in enumerate(source_steps):
            token=''.join(step['label'].split())
            later_input=any(''.join(s['label'].split()).endswith('입력') for s in source_steps[index+1:])
            prior_input=index>0 and ''.join(source_steps[index-1]['label'].split()).endswith('입력')
            if token.endswith('선택'):role,rule='SELECT_OBJECT','LGT-SELECT'
            elif token.endswith('입력'):role,rule='INPUT_INFORMATION','LGT-INPUT-WHOLE-OBJECT'
            elif token=='저장':role,rule='SAVE_INFORMATION','LGT-SAVE'
            elif token=='완료확인':role,rule='INSPECT_COMPLETION','LGT-CHECK'
            elif token=='종료':role,rule='END_WORKFLOW','LGT-END-CONDITIONAL'
            elif token=='등록' and prior_input and not later_input:role,rule='COMMIT_REGISTRATION','LGT-REGISTER-COMMIT'
            elif token=='등록' and later_input and not prior_input:role,rule='INITIATE_REGISTRATION','LGT-REGISTER-INITIATE'
            elif index==0 and step.get('menu_screen_name')==step['label']:role,rule='ENTER_CONTEXT','LGT-ENTER'
            else:role,rule=None,'LGT-UNRESOLVED'
            if role is None:unresolved.append(step['id'])
            if role=='END_WORKFLOW' and not step.get('direct_end_definition'):conditional.append(step['id'])
            rows.append(dict(required_step_id=step['id'],source_label=step['label'],source_order=step['step_order'],
                allowed_aliases=copy.deepcopy(step.get('allowed_aliases',[])),logical_role=role,rule_id=rule,
                logical_context=dict(name=step['menu_screen_name'],allowed_aliases=copy.deepcopy(step.get('menu_screen_aliases',[]))),
                declared_action_type=copy.deepcopy(step.get('action_type')),
                physical_screen=copy.deepcopy(step.get('screen_context')),end_definition=copy.deepcopy(step.get('direct_end_definition')),
                uncertainty='END_REALIZATION_NOT_EXHAUSTIVELY_DEFINED' if step['id'] in conditional else None,
                source_only=True))
        processes.append(dict(id=process['id'],business_name=process.get('business_name',''),procedures=rows))
    return dict(contract=CONTRACT,run_mode='DEVELOPMENT',approved_for_official=False,
        processes=processes,required_count=sum(len(p['procedures']) for p in processes),
        source_intent_unresolved_ids=unresolved,conditional_end_ids=conditional,
        source_semantics='LOGICAL_BUSINESS_PROCEDURES_NOT_PHYSICAL_UI_BINDINGS',
        no_generated_input=True,actual_score_computed=False)

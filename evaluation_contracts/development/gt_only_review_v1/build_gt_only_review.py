"""GT-only EVALUATION schema review. No backend/model/raw/output/result imports.
This script never supplies GT to any model, serializer, inference or scorer.
"""
from pathlib import Path
import copy
import csv
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
SOURCE_GT = Path('/Users/sooeunkim/workspace/RainbowKTL/evaluation_contracts/development/m02_td04_v1.json')

def canonical(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

RULES = {
    'version':'td04-gt-only-annotation-1',
    'input_policy':'TD04_ORIGINAL_TEXT_AND_GENERIC_TAXONOMY_ONLY',
    'never_inputs':['generated maps','raw events','provenance logs','model output','match results','scores'],
    'taxonomy':['PAGE_ENTER','MENU_ENTER','QUERY','VIEW','DETAIL_OPEN','SELECT','INPUT',
        'SAVE','REGISTER','UPDATE','CONFIRM','RESULT_CHECK','POPUP_OPEN','POPUP_CLOSE','UNRESOLVED'],
    'action_rules':[
        {'id':'GT-A01','source_condition':'procedure ends with explicit 선택','action':'SELECT','scope':'logical selection intention only'},
        {'id':'GT-A02','source_condition':'procedure ends with explicit 입력','action':'INPUT','scope':'logical input intention only; no invented fields'},
        {'id':'GT-A03','source_condition':'procedure is exactly 저장','action':'SAVE','scope':'explicit save intention; no HTTP claim'},
        {'id':'GT-A04','source_condition':'procedure is exactly 완료 확인','action':'RESULT_CHECK','scope':'explicit completion-result inspection intention; no passive outcome accepted as direct evidence'},
        {'id':'GT-A05','source_condition':'procedure is exactly 등록, prior procedure explicitly inputs information, no later input procedure','action':'REGISTER','scope':'post-input registration intention only; no endpoint or UI mechanism claim'},
        {'id':'GT-U01','source_condition':'standalone first screen/menu name without verb','action':None,'reason':'PAGE_ENTER vs MENU_ENTER not specified'},
        {'id':'GT-U02','source_condition':'등록 precedes input and save','action':None,'reason':'registration initiation/form entry vs completed register action not specified'},
        {'id':'GT-U03','source_condition':'procedure is exactly 종료','action':None,'reason':'task termination vs popup close/navigation/other explicit operation not specified'},
        {'id':'GT-U99','source_condition':'otherwise','action':None,'reason':'insufficient explicit source semantics'}],
    'screen_policy':'Logical workflow names do not establish page_path/page_title/menu_path/popup_title. Require original explicit typed identifiers; never infer from generated or raw evidence.',
    'target_policy':'Preserve original label, step ID/order and aliases exactly. Do not strip object words or add output-compatible aliases.',
    'readiness_policy':'Any unresolved typed screen/action blocks full executable schema. Partial review is NOT an evaluation input.'
}

def action_review(label, labels, index):
    compact = ''.join(label.split())
    if compact.endswith('선택'):
        return 'SELECT','GT-A01','Explicit selection verb in original procedure'
    if compact.endswith('입력'):
        return 'INPUT','GT-A02','Explicit input verb in original procedure; individual fields unspecified'
    if compact == '저장':
        return 'SAVE','GT-A03','Explicit save verb; transport/UI implementation unspecified'
    if compact == '완료확인':
        return 'RESULT_CHECK','GT-A04','Logical completion-result inspection; actual UI confirmation/outcome mechanism unspecified'
    if compact == '등록':
        prior_input = index > 0 and ''.join(labels[index-1].split()).endswith('입력')
        later_input = any(''.join(value.split()).endswith('입력') for value in labels[index+1:])
        if prior_input and not later_input:
            return 'REGISTER','GT-A05','Explicit post-input registration intention; no UI/control inference'
        return None,'GT-U02','등록 appears before content input/save; initiation mechanism is unspecified'
    if compact == '종료':
        return None,'GT-U03','Only logical task end is stated; no canonical termination operation is specified'
    if index == 0:
        return None,'GT-U01','Standalone logical screen/menu name; PAGE_ENTER vs MENU_ENTER unspecified'
    return None,'GT-U99','No unique generic action is justified by the original text'

def main():
    original=json.loads(SOURCE_GT.read_text())
    source=json.loads((HERE/'source_library_read.json').read_text())
    source_text=(HERE/'source_extracted_text.txt').read_text()
    page_sections=re.split(r'<PARSED TEXT FOR PAGE: (\d+) / \d+>',source_text)
    pages={int(page_sections[i]):page_sections[i+1] for i in range(1,len(page_sections),2)}
    partial=copy.deepcopy(original)
    partial.update(version='development-td04-gt-only-partial-v1',
        status='PARTIAL_GT_ONLY_NOT_FOR_MEASUREMENT',measurement_ready=False,
        approved_for_official=False,original_gt_sha256=sha(SOURCE_GT),
        source_text_sha256=sha(HERE/'source_extracted_text.txt'),source_binary_sha256=None,
        action_review_rules_version=RULES['version'],
        notice='GT-only partial annotations. Unresolved action/screen fields are deliberately null. This document is not wired to any evaluator and does not replace the frozen original TD-04.')
    rows=[];summaries=[]
    for process in partial['processes']:
        labels=[step['label'] for step in process['procedures']]
        source_pages=[number for number,text in pages.items() if re.search(r'\b'+re.escape(process['id'])+r'\b',text)]
        if len(source_pages)!=1:
            raise ValueError('Original source page reference is ambiguous')
        for index,step in enumerate(process['procedures']):
            action,rule,reason=action_review(step['label'],labels,index)
            step.update(action_type=action,screen_context=None,
                gt_only_annotation=dict(action_status='SOURCE_SUPPORTED_LOGICAL_ACTION' if action else 'UNRESOLVED',
                    action_rule_id=rule,action_reason=reason,
                    screen_status='UNRESOLVED_TYPED_IDENTIFIER_NOT_IN_SOURCE',
                    logical_workflow_entry_name=labels[0],
                    logical_workflow_entry_name_is_not_physical_screen=True,
                    original_menu_screen_name_is_workflow_context_only=True,
                    source_page=source_pages[0],source_step_token=step['label'],
                    source_sequence=' → '.join(labels),
                    not_direct_execution_evidence=True,measurement_ready=False))
            rows.append(dict(business_unit_id=process['id'],required_step_id=step['id'],
                step_order=step['step_order'],source_page=source_pages[0],
                source_procedure=step['label'],source_sequence=' → '.join(labels),
                action_type=action or '',action_rule_id=rule,action_status=step['gt_only_annotation']['action_status'],
                action_reason=reason,screen_kind='',screen_value='',screen_status='UNRESOLVED_TYPED_IDENTIFIER_NOT_IN_SOURCE',
                original_menu_screen_name=step['menu_screen_name'],measurement_ready=False))
        summaries.append(dict(business_unit_id=process['id'],required_count=len(labels),
            source_supported_actions=sum(bool(s['action_type']) for s in process['procedures']),
            unresolved_actions=sum(not s['action_type'] for s in process['procedures']),
            typed_screens_resolved=0,measurement_ready=False))
    # Conservation check: no changes to authoritative procedure identity/content/aliases.
    for before,after in zip(original['processes'],partial['processes']):
        for b,a in zip(before['procedures'],after['procedures']):
            for key,value in b.items():
                if a[key]!=value:raise ValueError('Original GT content modified')
    outputs={'review_rules.json':RULES,'td04_semantic_partial.json':partial,'summary.json':summaries}
    for name,value in outputs.items():(HERE/name).write_bytes(canonical(value))
    with (HERE/'procedure_review.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    manifest=dict(stage='GT_ONLY_REVIEW_BEFORE_REMEASUREMENT',run_mode='DEVELOPMENT',
        measurement_ready=False,not_for_evaluator_input=True,replaces_current_gt=False,
        source_library_file_id=source['library_file_id'],source_file_id=source['file_id'],
        source_name=source['name'],source_size_bytes=source['size_bytes'],source_version_id=source['version_id'],
        source_binary_sha256=None,source_binary_materialization_status='DOWNLOAD_FAILED; Library full text read completed',
        source_gt_path=str(SOURCE_GT),source_gt_sha256=sha(SOURCE_GT),
        input_policy=RULES['input_policy'],never_inputs=RULES['never_inputs'],
        files={name:sha(HERE/name) for name in ['build_gt_only_review.py','source_library_read.json','source_extracted_text.txt',
            'review_rules.json','td04_semantic_partial.json','summary.json','procedure_review.csv']},
        required_count=len(rows),source_supported_actions=sum(bool(r['action_type']) for r in rows),
        unresolved_actions=sum(not r['action_type'] for r in rows),typed_screens_resolved=0,
        typed_screens_unresolved=len(rows),full_schema_ready_steps=0,
        independent_verification='PENDING',actual_score_computed=False,
        reviewer_limitation='Current review reads only GT/source/taxonomy. This conversation includes prior development history; no claim of a fresh historically blinded reviewer.')
    (HERE/'review_manifest.json').write_bytes(canonical(manifest))
    print(json.dumps(dict(required_count=len(rows),source_supported_actions=manifest['source_supported_actions'],
        unresolved_actions=manifest['unresolved_actions'],typed_screens_unresolved=len(rows),
        measurement_ready=False,review_manifest_sha256=sha(HERE/'review_manifest.json'),summary=summaries),ensure_ascii=False,indent=2))

if __name__=='__main__':main()

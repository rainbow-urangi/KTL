"""V6.2 notebook cell 24의 GT-independent process export 구간."""
import re
from collections import Counter, defaultdict
import numpy as np
import pandas as pd


def export_processes(context):
    df=context['df'];segdf=context['segdf'];workflow_df=context['workflow_df']
    workflow_members=context['workflow_members'];safe_str=context['safe_str'];DATASET_NAME=context['DATASET_NAME']
    GENERIC_DISPLAY_TOKENS = {'', 'click', 'change', 'paste', 'value_reflection', 'api_transaction', 'api_transaction_error', 'api_transaction_timeout', 'grid_cell_click', 'grid_context_enrichment', 'popup_open', 'popup_close', 'popup_structure', 'page_view', 'page_close', 'collector_boot', 'screen_change', 'dom_event', 'exbuilder6'}
    TECHNICAL_VALUE_RE = re.compile('^(?:glb-[A-Za-z0-9_-]+|col_\\d+|SP\\d+|WP\\d+|S\\d+|W\\d+|[A-Z][A-Z0-9_]{2,}|[0-9a-f]{12,})$', flags=re.I)
    ROW_CELL_RE = re.compile('\\d+\\s*행\\s*\\d+\\s*열', flags=re.I)
    ERROR_TEXT_RE = re.compile('(ORA-\\d+|오류|에러|필수\\s*열|필수\\s*입력|유효하지\\s*않|조회된\\s*내역이\\s*없|ERR-SRV|timeout)', flags=re.I)
    PURE_VALUE_RE = re.compile('^\\s*(?:[-+]?\\d+(?:[.,]\\d+)*|\\d{4}[-./년]\\s*\\d{1,2}.*|[FMYN]|true|false)\\s*$', flags=re.I)
    
    def _safe_session(v):
        s = safe_str(v)
        return s if s else '__NO_SESSION__'
    
    def _is_readable_label_candidate(x):
        s = safe_str(x)
        if not s:
            return False
        sl = s.lower()
        if sl in GENERIC_DISPLAY_TOKENS:
            return False
        if len(s) < 2 or len(s) > 55:
            return False
        if TECHNICAL_VALUE_RE.fullmatch(s):
            return False
        if ROW_CELL_RE.search(s):
            return False
        if ERROR_TEXT_RE.search(s):
            return False
        if PURE_VALUE_RE.fullmatch(s):
            return False
        if re.fullmatch('[\\W_]+', s):
            return False
        if s.startswith('http://') or s.startswith('https://') or s.startswith('/'):
            return False
        return True
    
    def _add_label_candidate(counter, value, weight):
        s = safe_str(value)
        if _is_readable_label_candidate(s):
            counter[s] += float(weight)
    
    def _label_counter_for_events(ev):
        """
        화면 표시용 label 후보.
        associated_label을 가장 우선하고 element_text를 보조로 사용.
        input_data 자체는 node 이름 후보로 사용하지 않는다.
        """
        c = Counter()
        if 'associated_label' in ev.columns:
            for v in ev['associated_label'].tolist():
                _add_label_candidate(c, v, 5.0)
        if 'element_text' in ev.columns:
            for v in ev['element_text'].tolist():
                _add_label_candidate(c, v, 2.0)
        if 'interaction_type' in ev.columns and 'element_text' in ev.columns:
            for (_, r) in ev.iterrows():
                it = safe_str(r.get('interaction_type')).lower()
                if it in {'click', 'grid_cell_click', 'popup_open'}:
                    _add_label_candidate(c, r.get('element_text'), 1.5)
        return c
    
    def _pick_best_label(counter, fallback):
        if not counter:
            return fallback
        ranked = sorted(counter.items(), key=lambda kv: (kv[1], 1 if re.search('[가-힣]', kv[0]) else 0, min(len(kv[0]), 30)), reverse=True)
        return ranked[0][0] if ranked else fallback
    
    def _segment_events(segment_idx):
        r = seg_by_idx.loc[int(segment_idx)]
        st = int(r['start_global_idx'])
        en = int(r['end_global_idx'])
        ev = df.iloc[st:en + 1].copy()
        if 'stream_id' in ev.columns:
            ev = ev[ev['stream_id'].astype(str) == safe_str(r['stream_id'])]
        ev = ev.sort_values(['event_time_parsed', 'global_event_idx'], kind='stable')
        return ev
    
    def _source_redacted(raw_value):
        s = safe_str(raw_value).upper()
        return int('[REDACTED]' in s or '[IDENTITY_CONTEXT]' in s)
    
    def _input_kind(interaction_type):
        t = safe_str(interaction_type).lower()
        if t in {'change', 'paste'}:
            return 'direct_input'
        if t in {'click', 'grid_cell_click'}:
            return 'selection'
        if t == 'value_reflection':
            return 'reflected_value'
        return 'observed_value'
    seg_by_idx = segdf.set_index('segment_idx', drop=False)
    workflow_member_map = {}
    for (pos, (_, wr)) in enumerate(workflow_df.iterrows()):
        widx = int(wr['workflow_idx'])
        if pos < len(workflow_members):
            workflow_member_map[widx] = np.asarray(workflow_members[pos], dtype=int)
        else:
            start_seg = int(wr['segment_start'])
            end_seg = int(wr['segment_end'])
            cand = segdf[(segdf['stream_id'].astype(str) == safe_str(wr['stream_id'])) & (segdf['segment_idx'] >= start_seg) & (segdf['segment_idx'] <= end_seg)].sort_values('start_global_idx')
            workflow_member_map[widx] = cand['segment_idx'].astype(int).to_numpy()
    segment_fragments = {}
    for (seg_idx, sr) in seg_by_idx.iterrows():
        ev = _segment_events(seg_idx)
        if len(ev) == 0:
            segment_fragments[int(seg_idx)] = []
            continue
        if 'session_id' not in ev.columns:
            ev = ev.copy()
            ev['_v42_session'] = '__NO_SESSION__'
        else:
            ev = ev.copy()
            ev['_v42_session'] = ev['session_id'].map(_safe_session)
        session_vals = ev['_v42_session'].tolist()
        run_ids = []
        run_no = -1
        prev = None
        for s in session_vals:
            if prev is None or s != prev:
                run_no += 1
            run_ids.append(run_no)
            prev = s
        ev['_v42_session_run'] = run_ids
        fragments = []
        for (frag_no, (_, frag_ev)) in enumerate(ev.groupby('_v42_session_run', sort=False), start=1):
            frag_ev = frag_ev.copy()
            session_id = safe_str(frag_ev['_v42_session'].iloc[0])
            label_counter = _label_counter_for_events(frag_ev)
            sp = safe_str(sr.get('segment_prototype')) or 'SP_UNASSIGNED'
            display_label = _pick_best_label(label_counter, sp)
            inputs = []
            if 'input_data' in frag_ev.columns:
                for (_, er) in frag_ev.iterrows():
                    raw_value = safe_str(er.get('input_data'))
                    if not raw_value:
                        continue
                    label = safe_str(er.get('associated_label')) or safe_str(er.get('element_text')) or safe_str(er.get('data_testid')) or '입력값'
                    inputs.append({'event_id': safe_str(er.get('event_id')) or safe_str(er.get('id')), 'event_time': er.get('event_time_parsed', er.get('event_time')), 'interaction_type': safe_str(er.get('interaction_type')), 'input_kind': _input_kind(er.get('interaction_type')), 'input_label': label, 'input_value': raw_value, 'is_direct_user_input': int(_input_kind(er.get('interaction_type')) == 'direct_input'), 'is_source_redacted': _source_redacted(raw_value)})
            fragments.append({'segment_idx': int(seg_idx), 'segment_id': safe_str(sr.get('segment_id')), 'segment_prototype': sp, 'session_id': session_id, 'fragment_no': frag_no, 'start_time': frag_ev['event_time_parsed'].min(), 'end_time': frag_ev['event_time_parsed'].max(), 'event_count': int(len(frag_ev)), 'prototype_confidence': float(sr.get('segment_prototype_confidence', 0) or 0), 'display_label': display_label, 'label_counter': label_counter, 'evidence': safe_str(sr.get('evidence')), 'inputs': inputs})
        segment_fragments[int(seg_idx)] = fragments
    export_instances_source = []
    for (_, wr) in workflow_df.sort_values('workflow_idx').iterrows():
        widx = int(wr['workflow_idx'])
        workflow_id = safe_str(wr['workflow_id'])
        wp = safe_str(wr.get('workflow_prototype')) or 'WP_UNASSIGNED'
        model_id = f'{DATASET_NAME}:{wp}'
        seg_ids = workflow_member_map.get(widx, np.array([], dtype=int))
        fragment_seq = []
        for seg_idx in seg_ids:
            fragment_seq.extend(segment_fragments.get(int(seg_idx), []))
        if not fragment_seq:
            continue
        parts = []
        current = []
        current_session = None
        for frag in fragment_seq:
            sid = frag['session_id']
            if current and sid != current_session:
                parts.append(current)
                current = []
            if not current:
                current_session = sid
            current.append(frag)
        if current:
            parts.append(current)
        for (part_no, part) in enumerate(parts, start=1):
            export_instances_source.append({'source_workflow_idx': widx, 'source_workflow_id': workflow_id, 'workflow_prototype': wp, 'model_id': model_id, 'stream_id': safe_str(wr.get('stream_id')), 'session_id': part[0]['session_id'], 'session_part': part_no, 'fragments': part, 'source_workflow_prototype_confidence': float(wr.get('workflow_prototype_confidence', 0) or 0)})
    
    def _compress_fragment_sequence(fragments):
        steps = []
        for frag in fragments:
            sp = frag['segment_prototype']
            if steps and steps[-1]['segment_prototype'] == sp:
                step = steps[-1]
                step['fragments'].append(frag)
                step['repeat_count'] += 1
                step['event_count'] += frag['event_count']
                step['end_time'] = max(step['end_time'], frag['end_time'])
                step['prototype_confidences'].append(frag['prototype_confidence'])
                step['label_counter'].update(frag['label_counter'])
                if frag['evidence']:
                    step['evidence_counter'][frag['evidence']] += 1
                step['inputs'].extend(frag['inputs'])
            else:
                ec = Counter()
                if frag['evidence']:
                    ec[frag['evidence']] += 1
                steps.append({'segment_prototype': sp, 'fragments': [frag], 'repeat_count': 1, 'start_time': frag['start_time'], 'end_time': frag['end_time'], 'event_count': frag['event_count'], 'prototype_confidences': [frag['prototype_confidence']], 'label_counter': Counter(frag['label_counter']), 'evidence_counter': ec, 'inputs': list(frag['inputs'])})
        return steps
    instance_rows = []
    instance_step_rows = []
    node_input_rows = []
    node_stats = defaultdict(lambda : {'step_count': 0, 'source_segment_count': 0, 'instance_ids': set(), 'positions': [], 'event_counts': [], 'repeat_counts': [], 'confidences': [], 'label_counter': Counter(), 'evidence_counter': Counter()})
    edge_counts = Counter()
    outgoing_counts = Counter()
    input_seq = 0
    instance_seq = 0
    instance_step_seq = 0
    for inst_src in export_instances_source:
        instance_seq += 1
        wp = inst_src['workflow_prototype']
        model_id = inst_src['model_id']
        source_workflow_id = inst_src['source_workflow_id']
        instance_id = f"{DATASET_NAME}:{source_workflow_id}:P{inst_src['session_part']:02d}"
        steps = _compress_fragment_sequence(inst_src['fragments'])
        prev_node_id = None
        instance_input_count = 0
        source_segment_ids_all = []
        for (step_order, step) in enumerate(steps, start=1):
            instance_step_seq += 1
            sp = step['segment_prototype']
            node_id = f'{model_id}:{sp}'
            instance_step_id = f'IS{instance_step_seq:08d}'
            source_segment_ids = []
            for frag in step['fragments']:
                sid = frag['segment_id']
                if sid and sid not in source_segment_ids:
                    source_segment_ids.append(sid)
            source_segment_ids_all.extend(source_segment_ids)
            display_label = _pick_best_label(step['label_counter'], sp)
            representative_evidence = ''
            if step['evidence_counter']:
                representative_evidence = step['evidence_counter'].most_common(1)[0][0]
            avg_seg_conf = float(np.mean(step['prototype_confidences'])) if step['prototype_confidences'] else 0.0
            instance_step_rows.append({'instance_step_id': instance_step_id, 'instance_id': instance_id, 'model_id': model_id, 'source_workflow_id': source_workflow_id, 'session_id': inst_src['session_id'], 'step_order': step_order, 'node_id': node_id, 'segment_prototype': sp, 'display_label': display_label, 'repeat_count': int(step['repeat_count']), 'source_segment_ids': '|'.join(source_segment_ids), 'start_time': step['start_time'], 'end_time': step['end_time'], 'event_count': int(step['event_count']), 'avg_segment_prototype_confidence': avg_seg_conf, 'input_count': int(len(step['inputs'])), 'representative_evidence': representative_evidence})
            stat = node_stats[model_id, sp]
            stat['step_count'] += 1
            stat['source_segment_count'] += len(source_segment_ids)
            stat['instance_ids'].add(instance_id)
            stat['positions'].append(step_order)
            stat['event_counts'].append(step['event_count'])
            stat['repeat_counts'].append(step['repeat_count'])
            stat['confidences'].append(avg_seg_conf)
            stat['label_counter'].update(step['label_counter'])
            if representative_evidence:
                stat['evidence_counter'][representative_evidence] += 1
            if prev_node_id is not None:
                edge_counts[model_id, prev_node_id, node_id] += 1
                outgoing_counts[model_id, prev_node_id] += 1
            prev_node_id = node_id
            seen_in_step = set()
            for inp in step['inputs']:
                dedup_key = (inp['event_id'], inp['input_label'], inp['input_value'], inp['input_kind'])
                if dedup_key in seen_in_step:
                    continue
                seen_in_step.add(dedup_key)
                input_seq += 1
                instance_input_count += 1
                node_input_rows.append({'input_id': f'I{input_seq:08d}', 'instance_id': instance_id, 'instance_step_id': instance_step_id, 'model_id': model_id, 'node_id': node_id, 'source_workflow_id': source_workflow_id, 'session_id': inst_src['session_id'], 'step_order': step_order, 'segment_prototype': sp, 'source_segment_ids': '|'.join(source_segment_ids), 'event_id': inp['event_id'], 'event_time': inp['event_time'], 'interaction_type': inp['interaction_type'], 'input_kind': inp['input_kind'], 'input_label': inp['input_label'], 'input_value': inp['input_value'], 'is_direct_user_input': inp['is_direct_user_input'], 'is_source_redacted': inp['is_source_redacted']})
        start_time = min((frag['start_time'] for frag in inst_src['fragments']))
        end_time = max((frag['end_time'] for frag in inst_src['fragments']))
        instance_rows.append({'instance_id': instance_id, 'model_id': model_id, 'source_workflow_id': source_workflow_id, 'workflow_prototype': wp, 'stream_id': inst_src['stream_id'], 'session_id': inst_src['session_id'], 'session_part': int(inst_src['session_part']), 'start_time': start_time, 'end_time': end_time, 'compressed_step_count': int(len(steps)), 'source_segment_count': int(len(set(source_segment_ids_all))), 'source_workflow_prototype_confidence': inst_src['source_workflow_prototype_confidence'], 'input_count': int(instance_input_count)})
    process_instances = pd.DataFrame(instance_rows)
    process_instance_steps = pd.DataFrame(instance_step_rows)
    process_node_inputs = pd.DataFrame(node_input_rows)
    
    node_rows = []
    for ((model_id, sp), stat) in node_stats.items():
        node_id = f'{model_id}:{sp}'
        display_label = _pick_best_label(stat['label_counter'], sp)
        representative_evidence = ''
        if stat['evidence_counter']:
            representative_evidence = stat['evidence_counter'].most_common(1)[0][0]
        node_inputs = process_node_inputs[process_node_inputs['node_id'] == node_id] if len(process_node_inputs) else pd.DataFrame()
        node_rows.append({'node_id': node_id, 'model_id': model_id, 'segment_prototype': sp, 'display_label': display_label, 'support_step_count': int(stat['step_count']), 'support_segment_count': int(stat['source_segment_count']), 'support_instance_count': int(len(stat['instance_ids'])), 'avg_step_position': float(np.mean(stat['positions'])) if stat['positions'] else 0.0, 'avg_event_count': float(np.mean(stat['event_counts'])) if stat['event_counts'] else 0.0, 'avg_repeat_count': float(np.mean(stat['repeat_counts'])) if stat['repeat_counts'] else 1.0, 'avg_prototype_confidence': float(np.mean(stat['confidences'])) if stat['confidences'] else 0.0, 'input_count': int(len(node_inputs)), 'direct_input_count': int(node_inputs['is_direct_user_input'].sum()) if len(node_inputs) else 0, 'representative_evidence': representative_evidence})
    process_nodes = pd.DataFrame(node_rows)
    if len(process_nodes):
        process_nodes = process_nodes.sort_values(['model_id', 'avg_step_position', 'support_instance_count'], ascending=[True, True, False]).reset_index(drop=True)
        process_nodes['sort_order'] = process_nodes.groupby('model_id').cumcount() + 1
    edge_rows = []
    for (edge_no, ((model_id, from_node_id, to_node_id), cnt)) in enumerate(sorted(edge_counts.items()), start=1):
        denom = max(outgoing_counts[model_id, from_node_id], 1)
        edge_rows.append({'edge_id': f'E{edge_no:08d}', 'model_id': model_id, 'from_node_id': from_node_id, 'to_node_id': to_node_id, 'transition_count': int(cnt), 'transition_ratio': float(cnt / denom), 'is_repeat': int(from_node_id == to_node_id)})
    process_edges = pd.DataFrame(edge_rows)
    model_rows = []
    if len(process_instances):
        for (model_id, g) in process_instances.groupby('model_id', sort=False):
            wp = safe_str(g['workflow_prototype'].iloc[0])
            ng = process_nodes[process_nodes['model_id'] == model_id] if len(process_nodes) else pd.DataFrame()
            eg = process_edges[process_edges['model_id'] == model_id] if len(process_edges) else pd.DataFrame()
            label_candidates = []
            if len(ng):
                ranked_nodes = ng.sort_values(['support_instance_count', 'support_step_count', 'avg_step_position'], ascending=[False, False, True])
                for label in ranked_nodes['display_label'].tolist():
                    label = safe_str(label)
                    if _is_readable_label_candidate(label) and label not in label_candidates:
                        label_candidates.append(label)
                    if len(label_candidates) >= 3:
                        break
            display_name = wp
            if label_candidates:
                display_name = f'{wp} · ' + ' / '.join(label_candidates)
            model_inputs = process_node_inputs[process_node_inputs['model_id'] == model_id] if len(process_node_inputs) else pd.DataFrame()
            model_steps = process_instance_steps[process_instance_steps['model_id'] == model_id] if len(process_instance_steps) else pd.DataFrame()
            model_rows.append({'model_id': model_id, 'dataset_name': DATASET_NAME, 'workflow_prototype': wp, 'display_name': display_name, 'instance_count': int(len(g)), 'node_count': int(len(ng)), 'edge_count': int(len(eg)), 'avg_compressed_step_count': float(g['compressed_step_count'].mean()), 'avg_source_segment_count': float(g['source_segment_count'].mean()), 'avg_prototype_confidence': float(g['source_workflow_prototype_confidence'].mean()), 'input_count': int(len(model_inputs)), 'direct_input_count': int(model_inputs['is_direct_user_input'].sum()) if len(model_inputs) else 0, 'first_seen': pd.to_datetime(g['start_time'], errors='coerce').min(), 'last_seen': pd.to_datetime(g['end_time'], errors='coerce').max()})
    process_models = pd.DataFrame(model_rows)
    if len(process_models):
        process_models = process_models.sort_values(['instance_count', 'input_count'], ascending=[False, False]).reset_index(drop=True)
    
    return {'process_models':process_models,'process_nodes':process_nodes,'process_edges':process_edges,
            'process_instances':process_instances,'process_instance_steps':process_instance_steps,'process_node_inputs':process_node_inputs}

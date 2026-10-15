"""재현 가능한 수치 비교와 남은 한계를 기록합니다."""
import json
from model.workflow_candidate_v1_1.src.run import write


def create_report(base,d,old,errors,oldcv):
    e=d['boundary'];a=e['v1_1'];b=e['v1_2'];s=b['segmentation'];c=d['clustering'];audit=d['process_map_audit']
    rows=[]
    for label,key in [('Boundary F1','all_development'),('R3 F1','internal_holdout')]:rows.append(dict(metric=label,v1_1=a[key]['tolerant']['f1'],v1_2=b[key]['tolerant']['f1']))
    for label,key in [('Predicted workflows','predicted_workflow_count'),('Exact segmentation /60','correct_segmentation_exact'),('Over-segmented execution','over_segmented_execution_count'),('Under-segmented execution','under_segmented_execution_count'),('Under-segmented predicted workflow','under_segmented_workflow_count')]:rows.append(dict(metric=label,v1_1=a['segmentation'][key],v1_2=s[key]))
    for label,oldkey,newval in [('Cluster count','cluster_count',c['cluster_count']),('Silhouette','silhouette',c['silhouette']),('DBI','dbi',c['dbi']),('BU consistency','bu_consistency',d['bu_consistency']),('Cluster purity','cluster_purity',d['cluster_purity']),('Merged BU pairs','merged_bu_pairs',d['merged_bu_pairs']),('Fragmented BUs','fragmented_bus',d['fragmented_bus']),('Mixed-risk process models','B_process_models',audit['B_models']),('Cross-BU GET/write mixed nodes','cross_business_method_collision_nodes',audit['cross_business_method_collision_nodes']),('All GET/write mixed nodes','all_read_write_collision_nodes',audit['all_read_write_collision_nodes'])]:rows.append(dict(metric=label,v1_1=float(old[oldkey]),v1_2=newval))
    write(base/'diagnostics/comparison.csv',rows)
    lines=['# Workflow candidate v1.2 DEVELOPMENT 보고서','',
           '**INTERNAL DEVELOPMENT HOLDOUT — NOT INDEPENDENT UNSEEN VALIDATION**','',
           '기존 v1/v1.1/V6.2/원본 dataset은 수정하지 않았다. 개발 dataset 866 events, R1/R2 학습·R3 내부 holdout, weighted BCE, seed/epoch/lr/threshold=0.5를 고정한 후보 한 종류를 검증했다. 공식 KTL 점수나 GT step은 사용하지 않았다.','',
           '## 변경','',
           'Projection 64 → GRU 64×1 → MLP 32 구조를 유지했다. 입력만 396→428차원으로 확장했다. popup lifecycle, 이전 사용자 조작, HTTP method/category/family change, completion→navigation 등을 32개 명시 feature로 추가했다.',
           '다음 popup/route/API 신호는 최대 1초·3개 이벤트를 보는 offline feature다. 다음 사용자 조작을 만나면 탐색을 중단해 그 조작의 결과를 앞선 click에 귀속하지 않는다. 실시간 causal 모델이라고 주장하지 않는다. R3는 이미 오류 분석에 사용되어 독립 검증이 아니다.',
           'page_close/collector_boot/popup_structure는 새 업무의 시작으로 허용하지 않는 generic lifecycle decoder를 적용했다. 해당 event를 삭제하지 않으며 앞 workflow evidence에 남긴다.',
           'Representation C의 기존 embedding encoder도 v1 가중치로 고정했다. 새 boundary가 정한 구간으로 pooling하는 범위만 변한다. 구성·0.25×4 weight·1152차원·Agglomerative/threshold grid 모두 동일하다.',
           'Process node identity는 generic action + HTTP method + normalized endpoint + page context + target role이다. 동일 identity의 인접 event는 압축하고 재등장한 identity는 같은 node를 재사용한다. 개별 network 요청마다 node를 만드는 방식이 아니다. canonical procedure에도 method/endpoint를 전달한다. 외부 M03 API는 수정하지 않았다.','',
           '## 기존 오류 5 execution','', '| Execution | 분류 |','|---|---|']
    for r in errors:lines.append(f"| {r['execution_id']} | {', '.join(r['categories'])} |")
    lines+=['','±10 event의 실제 timestamp/path/action/API/status/gap은 baseline_boundary_windows.csv에 기록했다. 분석 시에는 익명 execution과 boundary만 사용하고 BU/repetition 연결은 별도 post-hoc CSV에 저장했다.',
            '일반 원인: popup close 이후의 화면 탐색/배경 click을 다음 업무 시작으로 너무 일찍 판단하고, 실제 modal-trigger click의 시작을 놓쳤다. 다른 한 건은 session 종료 page_close를 업무 시작으로 판단했다. 긴 inactivity가 주된 근거라는 증거는 없었으며 해당 오류 지점 gap은 약 0.95~2.89초였다.',
            '이번 결과에서 terminal 종료 오류 한 건을 제거했다. 두 조기 경계/지연된 실제 시작 오류는 남는다. event 수 또는 workflow 수를 60에 맞추는 보정은 하지 않았다.','',
            '## 전체 비교','', '| 지표 | v1.1 | v1.2 |','|---|---:|---:|']
    for r in rows:
        fmt=lambda v:f'{v:.4f}' if isinstance(v,float) and not v.is_integer() else str(int(v))
        lines.append(f"| {r['metric']} | {fmt(r['v1_1'])} | {fmt(r['v1_2'])} |")
    lines+=['','Under-segmented execution은 병합에 포함된 실제 execution의 고유 수(4개), under-segmented predicted workflow는 둘 이상 execution을 포함한 예측 구간 수(2개)다. 이전 보고의 과소분할 2는 후자다.','',
            '| 모델/범위 | Precision | Recall | F1 |','|---|---:|---:|---:|']
    for version in e:
        for split in ['all_development','internal_holdout']:
            m=e[version][split]['tolerant'];lines.append(f"| {version}/{split} | {m['precision']:.4f} | {m['recall']:.4f} | {m['f1']:.4f} |")
    lines+=['','세션 시작 제외, 동일 source session 내 ±1 event 일대일 매칭이다. 정확한 segmentation 집계에는 tolerance를 적용하지 않는다. exact boundary 결과도 JSON에 함께 보관했다.','',
            '## Group 3-fold','', '| Fold | v1.1 F1 | v1.2 F1 |','|---|---:|---:|']
    for x,y in zip(oldcv,d['group_cv']):lines.append(f"| {y['fold']} | {x['neural']['f1']:.4f} | {y['neural']['f1']:.4f} |")
    oldmean=sum(x['neural']['f1'] for x in oldcv)/len(oldcv);newmean=sum(x['neural']['f1'] for x in d['group_cv'])/len(d['group_cv'])
    lines+=['',f'평균 {oldmean:.4f} → {newmean:.4f}. 동일 BU fold/seed, held BU 이벤트는 학습에서 제외했다. fold 2는 여전히 F1=0이며 새로운 업무 유형 일반화를 보증하지 않는다. 각 fold에서 평가 가능한 positive boundary 수가 7/6/9로 작다는 제한이 있다.',
            '추론 문맥은 해당 source session의 관찰 이벤트이고 label은 전달되지 않는다. 학습 feature는 train chunk 안에서만 계산하므로 heldout의 future event를 학습 feature로 읽지 않는다.','',
            '## 개선의 원인과 남은 혼합','',
            'lifecycle_guard_ablation.json은 generic 종료-event decoder가 이번 R3 segmentation 개선에 기여했음을 구분한다. main 신경망 logit만으로 두 조기 경계가 해결되었다고 주장하지 않는다. group 진단에서 얻은 개선과 terminal decoder 효과는 별개로 읽어야 한다.',
            f"Mixed-risk model은 {audit['B_models']}개로 남는다. 일정 조회/등록 및 명함 상세/등록의 mixed workflow는 여전히 존재한다. Cross-BU GET/write 동일-node 혼합은 {audit['cross_business_method_collision_nodes']}개, 같은 BU 내부까지 포함한 혼합도 {audit['all_read_write_collision_nodes']}개다.",
            'generator_only_ablation.json은 v1.1의 동일 구간·동일 cluster에 method-aware generator만 적용한 결과이고, boundary_only_ablation.json은 새 boundary에 이전 generator를 적용한 결과다. node 의미 보존 개선과 경계 개선을 구별한다. M02 정확도 영향 가능성을 설명하지만 GT나 공식 점수로 성공을 주장하지 않는다.',
            '모든 adoption gate를 충족하면 DEVELOPMENT 후보로 채택하되, exact 56/60·남은 혼합 2쌍·group fold 2 실패 때문에 unseen 준비 완료로 승격하지 않는다. 추가 데이터는 수집하지 않았다.','',
            f"**최종 판정: {d['conclusion']}**",'']
    (base/'diagnostics/development_report.md').write_text('\n'.join(lines),encoding='utf-8')

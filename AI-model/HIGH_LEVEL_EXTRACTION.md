# High-level Business Extraction Layer

기존 DB 학습과 embedding 추론은 그대로 실행할 수 있다.

```bash
python train_self_supervised.py
python infer_case_embeddings.py
```

외부 CSV는 표준 필드명을 실제 CSV 컬럼명에 매핑한 JSON 파일과 함께 사용한다.

```bash
python tools/profile_external_data.py \
  --csv ./data/external_events.csv \
  --mapping ./data/column_mapping.json

export DATA_SOURCE=csv
export CSV_PATH=./data/external_events.csv
export COLUMN_MAPPING_PATH=./data/column_mapping.json
python train_self_supervised.py
```

Boundary 및 추상 step type 라벨이 있으면 pretrained encoder를 fine-tuning한다.
라벨 CSV에는 `case_id,event_index,is_step_start,abstract_step_type` 컬럼이 필요하며
`abstract_step_type` 값은 비어 있어도 된다.

```bash
python train_step_extractor.py --labels ./data/step_labels.csv
```

학습된 extractor가 있으면 기본적으로 `MODEL_DIR/step_extractor.pt`를 지정한다.
지정하지 않으면 pretrained encoder의 학습되지 않은 head로 실행되며 품질 경고가 출력된다.

```bash
export STEP_MODEL_PATH=./artifacts/event_transformer_v0/step_extractor.pt
python infer_workflows.py --output ./artifacts/workflows.jsonl

python tools/cluster_embeddings.py
python tools/summarize_workflows.py \
  --workflows ./artifacts/workflows.jsonl \
  --clusters ./artifacts/event_transformer_v0/case_embedding_clusters.csv
```

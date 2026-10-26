# Unseen Development Validation Candidate snapshot

본 snapshot은 workflow_candidate_v1_2의 UNSEEN DEVELOPMENT VALIDATION 후보 동결입니다. 최종 제품 모델 동결 또는 공식 KTL 승인/성능 판정이 아닙니다.

가중치·기존 config·source dependency·개발 embedding/cluster evidence를 byte-identical 복사했습니다. 기존 파일과 inference/training/clustering parameter는 변경하지 않았고, 모델 실행·재학습·재군집화도 하지 않았습니다.

기존 v1.2에는 standalone preprocessing_config.json이 없었습니다. artifacts/preprocessing_config.json은 현재 코드의 전처리를 설명하는 메타데이터이며 런타임이 사용하는 새 설정이 아닙니다. source snapshot과 원래 설정이 실행 동작의 근거입니다.

DEVELOPMENT_CLUSTER_REFERENCE.json에 21개 cluster의 1152차원 centroid, 별도 L2-normalized centroid, 기존 medoid workflow ID, cluster size와 membership을 저장했습니다. Centroid는 float32 입력 vector의 float64 산술평균입니다. Medoid는 기존 generator와 같은 방식으로 검산했으며 기존 ID를 유지했습니다.

군집 알고리즘은 여전히 전체 입력을 재군집화하는 transductive Agglomerative입니다. 개발 결과의 선택 distance threshold 0.25와 원래 탐색 grid를 함께 고정 기록했습니다. 이를 unseen nearest-centroid rejection threshold로 해석하면 안 됩니다. 새 assignment/novelty rule은 이번 작업에서 정의하거나 구현하지 않았습니다.

현재 raw timestamp가 timezone 없는 값이면 기존 Python timestamp 변환은 host local timezone을 사용합니다. 검증 환경은 Asia/Seoul로 기록했으며 모델 자체의 시간 변환 코드는 바꾸지 않았습니다.

검증 중 parameter/weight/전처리를 조정하지 않습니다. 변경이 필요하면 별도 candidate 버전과 manifest를 생성합니다. snapshot 파일을 덮어쓰지 않습니다. 기존 src/run.py는 재학습/산출물 갱신 명령이므로 이 동결 후보에 대한 검증 작업에서 실행하지 않습니다.

상위 VALIDATION_CANDIDATE_MANIFEST.json의 전체 hash inventory로 원본과 snapshot을 검증할 수 있습니다. Source dependency도 source/model 아래에 보관했습니다. 이 source tree를 그대로 별도 checkout root로 사용하면 기존 import 경로를 유지할 수 있습니다.

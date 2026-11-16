# ml/config.py
from dataclasses import dataclass
import os


@dataclass
class DBConfig:
    host: str = os.getenv("ML_DB_HOST", "127.0.0.1")
    port: int = int(os.getenv("ML_DB_PORT", "3306"))
    user: str = os.getenv("ML_DB_USER", "root")
    password: str = os.getenv("ML_DB_PASSWORD", "")
    database: str = os.getenv("ML_DB_NAME", "flows_ml_db")
    charset: str = "utf8mb4"


@dataclass
class TrainConfig:
    rule_version: str = os.getenv("ACTIVITY_RULE_VERSION", "v0.2")
    cluster_model_version: str = os.getenv(
        "CLUSTER_MODEL_VERSION",
        "baseline_hdbscan_v0.2_clean_20260423",
    )

    min_seq_len_clean: int = int(os.getenv("MIN_SEQ_LEN_CLEAN", "5"))
    max_seq_len: int = int(os.getenv("MAX_SEQ_LEN", "256"))

    batch_size: int = int(os.getenv("BATCH_SIZE", "32"))
    epochs: int = int(os.getenv("EPOCHS", "20"))
    lr: float = float(os.getenv("LR", "0.0003"))

    d_model: int = int(os.getenv("D_MODEL", "128"))
    nhead: int = int(os.getenv("NHEAD", "4"))
    num_layers: int = int(os.getenv("NUM_LAYERS", "3"))
    dim_feedforward: int = int(os.getenv("DIM_FEEDFORWARD", "256"))
    dropout: float = float(os.getenv("DROPOUT", "0.1"))

    model_dir: str = os.getenv("MODEL_DIR", "./artifacts/event_transformer_v0")

    # Input/output options for both the existing DB pipeline and external POCs.
    data_source: str = os.getenv("DATA_SOURCE", "db")
    csv_path: str = os.getenv("CSV_PATH", "")
    column_mapping_path: str = os.getenv("COLUMN_MAPPING_PATH", "")
    boundary_threshold: float = float(os.getenv("BOUNDARY_THRESHOLD", "0.5"))
    step_model_path: str = os.getenv("STEP_MODEL_PATH", "")
    workflow_output_path: str = os.getenv(
        "WORKFLOW_OUTPUT_PATH",
        "./artifacts/workflows.jsonl",
    )

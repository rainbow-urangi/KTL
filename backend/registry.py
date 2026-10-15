"""평가 범위와 내부 담당 정보. 담당 정보는 공개 API에 전달하지 않습니다."""
from .evaluators import METRICS

MODES = {"REFERENCE", "OFFICIAL", "DEVELOPMENT"}
STATUSES = {"OFFICIAL_M06_BUNDLE_MISSING","NOT_CONFIGURED", "WAITING_FOR_DATA", "REFERENCE_READY", "READY",
            "BLOCKED", "INSUFFICIENT_DATA_FOR_CONSENSUS", "RUNNING", "COMPLETED", "REFERENCE_PARTIAL", "EXTERNAL_MODULE_PENDING", "ERROR"}
OWNERSHIP = {
    "M01": ("junior", "external_integration_only"),
    "M02": ("user", "full_evaluator"),
    "M03": ("shared", "core_generator_only"),
    "M04": ("junior", "external_integration_only"),
    "M05": ("user", "full_evaluator"),
    "M06": ("user", "full_evaluator"),
    "M07": ("junior", "external_integration_only"),
}
EXTERNAL = {"M01", "M04", "M07"}
VERSION = "evaluation-2.0"

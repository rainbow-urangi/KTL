"""Shared wire-input validation, without coercing malformed JSON values."""
from .evaluators import require


def require_string_enum(value, allowed, field, invalid_message):
    """Reject non-strings before membership (including unhashable list/dict)."""
    require(isinstance(value, str), f"Invalid type for {field}: expected string")
    require(value in allowed, invalid_message)
    return value

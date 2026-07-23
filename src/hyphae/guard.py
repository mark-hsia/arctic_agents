"""Short import path for output-integrity decorators."""

from .no_synthetic_data import forbid_synthetic_data as validate_output

__all__ = ["validate_output"]

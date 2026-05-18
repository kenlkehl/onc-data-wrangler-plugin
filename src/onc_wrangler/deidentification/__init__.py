"""Structured table de-identification utilities."""

from importlib import import_module

__all__ = [
    "ColumnDecision",
    "DeidentificationConfig",
    "DeidentificationResult",
    "classify_columns",
    "deidentify_dataframe",
    "load_table",
    "write_table",
]


def __getattr__(name):
    """Lazily expose table helpers without pre-importing the CLI module."""
    if name in __all__:
        module = import_module(".table", __name__)
        return getattr(module, name)
    raise AttributeError(name)

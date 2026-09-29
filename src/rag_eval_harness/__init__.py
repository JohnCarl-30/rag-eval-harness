"""RAG eval harness: RAGAS with a memory and a diff view."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("rag-eval-harness")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.2.0"

__all__ = ["__version__"]

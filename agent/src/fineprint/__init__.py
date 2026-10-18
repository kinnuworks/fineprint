"""FinePrint agent tools: MCP server, Hugging Face download guard and repo checker.

    import fineprint
    fineprint.guard("block")   # or "warn"

Talks to the FinePrint API at FINEPRINT_API (default http://localhost:8000).
"""
from .client import Api, ApiUnavailable, NotFound, normalize_model_id
from .hub_guard import FinePrintBlocked, check, guard, status, unguard

__version__ = "0.1.0"
__all__ = ["Api", "ApiUnavailable", "NotFound", "FinePrintBlocked", "check", "guard", "unguard",
           "status", "normalize_model_id", "__version__"]

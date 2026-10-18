"""`import fineprint.autoguard` turns the guard on from the environment.

FINEPRINT_GUARD=block|warn|off (unset means warn). FINEPRINT_USE=commercial|noncommercial
(unset means commercial). FINEPRINT_ALLOW=org/a,org/b is never blocked.
"""
import os

from .hub_guard import guard

guard(os.environ.get("FINEPRINT_GUARD") or "warn")

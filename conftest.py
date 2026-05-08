"""
Root-level conftest.py — adds backend/ to sys.path so all flat imports
inside backend modules (e.g. `from pipeline_support import ...`) resolve.
"""
import sys
import os

_BACKEND = os.path.join(os.path.dirname(__file__), "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

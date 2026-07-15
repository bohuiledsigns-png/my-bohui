"""V4+ AI Engine Package

This package re-exports all public names from the original ai_engine.py module
at the project root, PLUS provides V4 autonomous sales system modules.

Naming note: The original ai_engine.py lives at the project root. This package
(ai_engine/) shadows it in imports. We use importlib to load the original module
and re-export its public API, so existing code (app.py, etc.) continues to work.
"""
import os
import sys
import importlib.util

# ── Re-export public names from the original ai_engine.py ──────────
_this_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.dirname(_this_dir)
_orig_path = os.path.join(_root_dir, 'ai_engine.py')

if os.path.exists(_orig_path):
    _spec = importlib.util.spec_from_file_location('_ai_engine_root', _orig_path)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    for _attr in dir(_mod):
        if not _attr.startswith('_'):
            globals()[_attr] = getattr(_mod, _attr)
    # Also export internal functions needed by test scripts
    for _internal in ('_load_knowledge_context', '_detect_knowledge_intent'):
        if hasattr(_mod, _internal):
            globals()[_internal] = getattr(_mod, _internal)

# ── Convenience re-exports for sub-modules ────────────────────────
from .deal_prioritizer import DealPrioritizer
from .dynamic_pricing import DynamicPricing
from .conversion_ai_brain import ConversionBrain
from .autonomous_sender import AutonomousSender
from .revenue_scheduler import RevenueScheduler, run_scheduler_tick, start_v4_scheduler_background

"""AI Overlay 入口"""
from ai_overlay import test_all, start_services
import sys

if "--test" in sys.argv:
    test_all()
else:
    start_services()

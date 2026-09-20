import os
import sys

# Lets `python -m pytest backend/tests -v` (invoked from the project root, not
# from inside backend/) resolve `from app import ...` in the test files.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

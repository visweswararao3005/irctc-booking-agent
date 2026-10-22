"""
Root test runner shim forwarding execution to tests/test_system.py.
Maintains full backward compatibility with 'python test_system.py'.
"""
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
TESTS_DIR = ROOT_DIR / "tests"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from test_system import run_tests

if __name__ == "__main__":
    asyncio.run(run_tests())

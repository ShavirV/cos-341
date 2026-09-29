# run all tests under /tests sequentially
# simply from repo root: python -m test.py
import sys

import pytest

sys.exit(pytest.main(["tests", "-q"] + sys.argv[1:]))
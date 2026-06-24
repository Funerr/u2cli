from __future__ import annotations

import importlib
import sys

_canonical = importlib.import_module("androidtestclii")
sys.modules[__name__] = _canonical

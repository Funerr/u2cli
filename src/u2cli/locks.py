from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("androidtestclii.locks")
sys.modules[__name__] = _module

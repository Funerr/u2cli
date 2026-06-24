from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("androidtestclii.replay")
sys.modules[__name__] = _module

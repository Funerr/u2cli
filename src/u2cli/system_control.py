from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("androidtestclii.system_control")
sys.modules[__name__] = _module

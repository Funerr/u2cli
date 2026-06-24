from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("androidtestclii.app")
sys.modules[__name__] = _module

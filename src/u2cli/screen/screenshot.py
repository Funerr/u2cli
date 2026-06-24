from __future__ import annotations

import importlib
import sys

_module = importlib.import_module("androidtestclii.screen.screenshot")
sys.modules[__name__] = _module

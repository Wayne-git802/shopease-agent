"""Re-exports from contracts.py (shadowed by this package directory).

When Python sees both contracts.py and contracts/__init__.py,
the package takes precedence. This init re-exports everything
from the contracts.py module so `from agents.graph.contracts import X` works.
"""

import importlib.util
import sys
from pathlib import Path

# Load the contracts.py module with correct package context
_contracts_path = Path(__file__).resolve().parent.parent / "contracts.py"
_module_name = "agents.graph._contracts_module"

# Register in sys.modules with proper __package__ so relative imports work
_spec = importlib.util.spec_from_file_location(
    _module_name,
    str(_contracts_path),
    submodule_search_locations=[],
)
_mod = importlib.util.module_from_spec(_spec)
_mod.__package__ = "agents.graph"
sys.modules[_module_name] = _mod
_spec.loader.exec_module(_mod)

# Re-export everything
RoutingInput = _mod.RoutingInput
RoutingOutput = _mod.RoutingOutput
SearchNodeInput = _mod.SearchNodeInput
SearchNodeOutput = _mod.SearchNodeOutput
RecommendNodeInput = _mod.RecommendNodeInput
RecommendNodeOutput = _mod.RecommendNodeOutput
OrderNodeInput = _mod.OrderNodeInput
OrderNodeOutput = _mod.OrderNodeOutput
OpsNodeInput = _mod.OpsNodeInput
OpsNodeOutput = _mod.OpsNodeOutput
AnalyticsNodeInput = _mod.AnalyticsNodeInput
AnalyticsNodeOutput = _mod.AnalyticsNodeOutput
ChatNodeInput = _mod.ChatNodeInput
ChatNodeOutput = _mod.ChatNodeOutput
ResponseNodeInput = _mod.ResponseNodeInput
ResponseNodeOutput = _mod.ResponseNodeOutput
MergeNodeInput = _mod.MergeNodeInput
MergeNodeOutput = _mod.MergeNodeOutput
EvalHook = _mod.EvalHook

"""Re-evaluate ONLY the layout group of the it5 full run from saved outputs,
with the kdl layout adapter aliased to our patched pipeline name. No GPU."""
import sys
sys.path.insert(0, '.'); sys.path.insert(0, 'parsebench/src')
from parse_bench.evaluation.layout_adapters import registry as R

# alias: whatever adapter is registered for the base name also serves the patched name
base = R.get_pipeline("kdl_frontier_nano") if hasattr(R, "get_pipeline") else None
ads = R.list_layout_adapters()
print("registered adapters:", ads)
src_name = "kdl_frontier_nano"
if src_name in ads:
    factory = ads[src_name] if isinstance(ads, dict) else None
    if factory is None:
        import parse_bench.evaluation.layout_adapters.adapters as A
        import inspect
        for n, fn in vars(A).items():
            if callable(fn) and getattr(fn, "_adapter_name", "") == src_name:
                factory = fn; break
    R.register_layout_adapter("kdl_frontier_nano_patched", factory) if factory else sys.exit("no factory found")
    print("aliased kdl_frontier_nano -> kdl_frontier_nano_patched")
else:
    sys.exit(f"{src_name} not in registry: {ads}")

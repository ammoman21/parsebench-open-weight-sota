"""
`ourparser` — our patched markdown emission for the ParseBench pipeline
`KDL-Frontier-Parser-nano`.

Two modules:

* `ourparser.emission` — the patched emission logic, as pure functions of a page-element
  list. Importable on its own; needs no endpoint and no GPU. This is what the no-GPU
  replay measurement scores.
* `ourparser.provider` — a subclass of the vendored ParseBench provider that uses that
  emission, plus registration of two new pipeline names. Importing it registers them.

Nothing under `parsebench/src/` is modified. `ourparser.provider` is imported lazily so
that `import ourparser.emission` does not pull in the provider registry.
"""

__all__ = ["emission", "provider"]

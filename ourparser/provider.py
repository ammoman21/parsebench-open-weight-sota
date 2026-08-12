"""
ParseBench provider and pipeline registration for the patched KDL-Frontier-nano
emission.

WHAT A "PROVIDER" AND A "PIPELINE" ARE HERE
-------------------------------------------
ParseBench (LlamaIndex's document-parsing benchmark) separates two names:

* a **provider** is a class that knows how to run some parser and hand back its output.
  Providers register themselves under a string key with
  `parse_bench.inference.providers.registry.register_provider`.
* a **pipeline** is a named configuration that points at a provider. Pipelines register
  with `parse_bench.inference.pipelines.register_pipeline`, and the benchmark's
  command line takes a pipeline name (`parse-bench run <pipeline_name> ...`).

Both registration functions are public and importable, so a new provider and a new
pipeline can be registered entirely from outside the `parse_bench` package. **Nothing
under `parsebench/src/` is modified by this module.** The one thing an external module
cannot do is make the benchmark's own command-line entry point import it, because that
entry point has no plugin hook; `ourparser/run_patched.py` is the two-line launcher that
closes that gap.

WHAT THIS PROVIDER CHANGES, AND WHAT IT DOES NOT
------------------------------------------------
It inherits every stage of the vendored pipeline — page rendering, the layout pass, the
crop/bucket step, all four recognition passes, retry and error handling — and replaces
exactly one thing: the function that turns the finished element list into markdown. It
also leaves the `pages` payload (each element's category, bounding box and text) exactly
as the vendored pipeline produced it, which is what makes the benchmark's Visual
Grounding dimension provably unaffected: that dimension is built from those fields at
`kdl_frontier_nano.py:3287-3296` and never from the markdown.

THE TWO SCOPED BINDINGS, AND WHY THEY ARE NOT AVOIDABLE
-------------------------------------------------------
Two things the patched pipeline needs are looked up as module globals by module-level
functions in the vendored file, where no subclass hook can reach them:

1. `NATIVE_LAYOUT_CATEGORY_MAP` is read by `_category_for_item`
   (`kdl_frontier_nano.py:763`), a module-level function called during layout parsing.
2. `_NanoEngine` is instantiated by name inside `KdlFrontierNanoProvider.run_inference`
   (`kdl_frontier_nano.py:3220`).

`patched_bindings()` below rebinds those two module attributes for the duration of one
document's inference and restores them afterwards. This is dependency injection through
the only seam the vendored file offers, not a behavioural patch: all the *behaviour*
lives in `ourparser/emission.py` as ordinary code. An upstream fix would instead edit
those two cited locations. The binding is scoped rather than applied at import so that
running the unpatched `kdl_frontier_nano` pipeline in the same process is unaffected.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, Dict, Iterator, List

from PIL import Image

from ourparser import emission
from ourparser.emission import EmissionConfig
from parse_bench.inference.pipelines import register_pipeline
from parse_bench.inference.providers.base import ProviderPermanentError
from parse_bench.inference.providers.parse import kdl_frontier_nano as K
from parse_bench.inference.providers.registry import register_provider
from parse_bench.schemas.pipeline import PipelineSpec
from parse_bench.schemas.pipeline_io import InferenceRequest, RawInferenceResult
from parse_bench.schemas.product import ProductType

#: Pipeline / provider name for the submitted patch set.
PATCHED_PIPELINE = "kdl_frontier_nano_patched"
#: Pipeline / provider name for the disclosed-but-not-submitted set.
AGGRESSIVE_PIPELINE = "kdl_frontier_nano_aggressive"


class PatchedNanoEngine(K._NanoEngine):
    """
    The vendored per-document engine with our markdown emission substituted.

    `_parse_page` is overridden only to keep a reference to the element dictionaries the
    vendored engine produces; the vendored implementation still does all the work. After
    `parse_pages` returns, those same dictionaries have been through
    `_nano_postprocess_element` in place, so they are the finished elements — including
    the `picture_path` field, which the pipeline's own `pages` payload drops and which
    the image markdown needs.
    """

    def __init__(self, *args: Any, config: EmissionConfig, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.config = config
        self._captured: List[Dict[str, Any]] = []

    async def _parse_page(  # type: ignore[override]
        self,
        client: Any,
        semaphore: asyncio.Semaphore,
        image: Image.Image,
        page_no: int,
    ) -> List[Dict[str, Any]]:
        elements = await super()._parse_page(client, semaphore, image, page_no)
        self._captured.extend(elements)
        return elements

    def rebuild_markdown(self, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Patched markdown for a finished element list.

        Exposed as its own method so the no-GPU replay harness can drive the exact code
        path live inference uses, feeding it elements read back from stored run
        artifacts.
        """
        full_md, markdown_pages = emission.build_markdown(elements, self.config)
        return {"markdown": full_md, "markdown_pages": markdown_pages}

    async def parse_pages(self, page_images: List[Image.Image]) -> dict:
        self._captured = []
        raw = await super().parse_pages(page_images)
        raw.update(self.rebuild_markdown(self._captured))
        return raw


@contextlib.contextmanager
def patched_bindings(config: EmissionConfig) -> Iterator[None]:
    """
    Scoped dependency injection for the two module globals described in the module
    docstring. Restores both on exit, including on exception.
    """
    old_map = K.NATIVE_LAYOUT_CATEGORY_MAP
    old_engine = K._NanoEngine

    def engine_factory(*args: Any, **kwargs: Any) -> PatchedNanoEngine:
        return PatchedNanoEngine(*args, config=config, **kwargs)

    if config.section_header_map_fix:
        K.NATIVE_LAYOUT_CATEGORY_MAP = emission.PATCHED_NATIVE_LAYOUT_CATEGORY_MAP
    K._NanoEngine = engine_factory  # type: ignore[assignment]
    try:
        yield
    finally:
        K.NATIVE_LAYOUT_CATEGORY_MAP = old_map
        K._NanoEngine = old_engine  # type: ignore[assignment]


def _config_from_pipeline_config(cfg: dict[str, Any]) -> EmissionConfig:
    """
    Read the emission configuration out of a pipeline's `config` dictionary.

    Defaults are the submitted set including the borderline gate relaxation; the
    aggressive pipeline overrides the two extra keys.
    """
    named = cfg.get("emission_set")
    if named == "genuine_abc":
        return emission.GENUINE_ABC
    if named == "genuine_abcd":
        return emission.GENUINE_ABCD
    if named == "aggressive_abc":
        return emission.aggressive(emission.GENUINE_ABC)
    if named == "aggressive_abcd":
        return emission.aggressive(emission.GENUINE_ABCD)
    if named == "baseline":
        return emission.BASELINE
    raise ProviderPermanentError(
        "pipeline config needs emission_set in "
        "{baseline, genuine_abc, genuine_abcd, aggressive_abc, aggressive_abcd}; "
        f"got {named!r}"
    )


@register_provider(PATCHED_PIPELINE)
class KdlFrontierNanoPatchedProvider(K.KdlFrontierNanoProvider):
    """
    `KDL-Frontier-Parser-nano` with the patched markdown emission of
    `ourparser.emission`. Serving requirements, environment variables and every
    inference stage are inherited unchanged from the vendored provider.
    """

    def __init__(self, provider_name: str, base_config: dict[str, Any] | None = None):
        super().__init__(provider_name, base_config)
        self.emission_config = _config_from_pipeline_config(self.base_config or {})

    def run_inference(
        self, pipeline: Any, request: InferenceRequest
    ) -> RawInferenceResult:
        with patched_bindings(self.emission_config):
            return super().run_inference(pipeline, request)


@register_provider(AGGRESSIVE_PIPELINE)
class KdlFrontierNanoAggressiveProvider(KdlFrontierNanoPatchedProvider):
    """
    The disclosed-but-not-submitted variant. Registered under its own name so the two
    cannot be confused in an output directory or a leaderboard row.
    """


def register() -> None:
    """
    Register both pipelines. Idempotent: `register_pipeline` raises on a duplicate name,
    which is caught so importing this module twice is harmless.
    """
    common = {
        "endpoint_url": "",  # supplied via KDL_NANO_ENDPOINT_URL
        "model": "",  # supplied via KDL_NANO_MODEL
        "dpi": 144,
        "timeout": 900,
    }
    for name, provider, emission_set in (
        (PATCHED_PIPELINE, PATCHED_PIPELINE, "genuine_abcd"),
        (AGGRESSIVE_PIPELINE, AGGRESSIVE_PIPELINE, "aggressive_abcd"),
    ):
        try:
            register_pipeline(
                PipelineSpec(
                    pipeline_name=name,
                    provider_name=provider,
                    product_type=ProductType.PARSE,
                    config={**common, "emission_set": emission_set},
                )
            )
        except ValueError:
            pass


register()

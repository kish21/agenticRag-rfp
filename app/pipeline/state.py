"""
PipelineState — the single shared state dict that flows through the LangGraph StateGraph.

No checkpointer is used, so fields do not need to be JSON-serialisable.
Pydantic output objects are stored directly; they are never pickled between nodes.

Phase 4 — parallel vendor execution via LangGraph Send:
  Vendor-iterating stages (retrieval / extraction / evaluation / explanation)
  fan out to N per-vendor nodes that run concurrently and each return a single
  {vendor_id: result} mapping. Without a state reducer, LangGraph would call
  the dict-valued state updates in serial order and the LAST writer wins
  (silently dropping N-1 vendors). The Annotated[dict, _merge_dicts] reducers
  below explicitly merge parallel branch outputs into the same dict.
"""
from typing import Any
from typing_extensions import TypedDict, Annotated


# ── State reducers ────────────────────────────────────────────────────────────
# LangGraph calls these with (existing_value_in_state, value_returned_by_node).
# Order of arguments matters: existing is LEFT, new is RIGHT.

def _merge_dicts(left: dict, right: dict) -> dict:
    """Merge two dicts; new keys from `right` win on conflict."""
    out = dict(left or {})
    out.update(right or {})
    return out


def _concat_lists(left: list, right: list) -> list:
    """Concatenate two lists in order."""
    return (left or []) + (right or [])


class PipelineState(TypedDict):
    # ── Fixed inputs (set once by _run_pipeline, never mutated by nodes) ─────
    run_id: str
    org_id: str
    rfp_id: str
    rfp_title: str
    rfp_filename: str
    rfp_bytes: bytes
    vendor_ids: list
    contract_value: float
    currency: str
    setup_id: str
    n_vendors: int

    # EvaluationSetup stored as a plain dict so nodes can reconstruct the
    # Pydantic model without importing it at the state layer.
    evaluation_setup_dict: dict

    # {vendor_id: (bytes, filename)}  — raw file payloads for ingestion
    vendor_file_map: dict

    # OrgSettings object (not serialised — in-memory only)
    org_settings: Any

    # ── Per-vendor Send payload ──────────────────────────────────────────────
    # Set by the fan-out edge for each parallel branch. Read by *_per_vendor
    # nodes. NOT meaningful at the top level (only inside a Send branch).
    vendor_id: str

    # ── Accumulated agent outputs (parallel-write safe via reducers) ─────────
    # Per-vendor nodes return {vendor_id: result}. The reducer merges all N
    # parallel returns into a single dict.
    retrieval_output_objects:  Annotated[dict, _merge_dicts]   # {vid: RetrievalOutput}
    extraction_output_objects: Annotated[dict, _merge_dicts]   # {vid: ExtractionOutput}
    evaluation_output_objects: Annotated[dict, _merge_dicts]   # {vid: EvaluationOutput}

    # Chunks accumulated across vendors during retrieval — used by explanation grounding
    source_chunks: Annotated[dict, _merge_dicts]               # {chunk_id: text}

    # Per-vendor narratives produced in parallel by explanation_per_vendor.
    # explanation_finalise reads this dict and stitches the final ExplanationOutput.
    vendor_narratives_accum: Annotated[dict, _merge_dicts]     # {vid: VendorNarrative}

    # Phase 4 failure isolation — if vendor X's stage fails, it appends here
    # and the other vendors keep going. Comparator/Decision treat these as
    # "no submission" rather than aborting the run.
    # Each entry: {"vendor_id": str, "stage": str, "error": str, "ts": str}
    failed_vendors: Annotated[list, _concat_lists]

    # Cross-vendor stages — single-writer, no reducer needed.
    comparator_output:  Any   # ComparatorOutput  | None
    decision_output:    Any   # DecisionOutput    | None
    explanation_output: Any   # ExplanationOutput | None

    # ── Control flow ─────────────────────────────────────────────────────────
    blocked: bool
    blocked_agent: str
    error_message: str

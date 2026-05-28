"""
PipelineState — the single shared state dict that flows through the LangGraph StateGraph.

No checkpointer is used, so fields do not need to be JSON-serialisable.
Pydantic output objects are stored directly; they are never pickled between nodes.
"""
from typing import Any, Optional
from typing_extensions import TypedDict


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

    # ── Accumulated agent outputs (Pydantic objects, set by each node) ───────
    # Nodes set these; downstream nodes read them.
    retrieval_output_objects: dict   # {vendor_id: RetrievalOutput}
    extraction_output_objects: dict  # {vendor_id: ExtractionOutput}
    evaluation_output_objects: dict  # {vendor_id: EvaluationOutput}
    comparator_output: Any           # ComparatorOutput | None
    decision_output: Any             # DecisionOutput   | None
    explanation_output: Any          # ExplanationOutput| None

    # Flat chunk map built during retrieval — used by explanation grounding
    source_chunks: dict              # {chunk_id: text}

    # ── Control flow ─────────────────────────────────────────────────────────
    blocked: bool
    blocked_agent: str
    error_message: str

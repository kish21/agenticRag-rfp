HR_AGENT_CONFIG = {
    "identity": {
        "agent_type": "hr",
        "agent_name": "HR Policy Assistant",
    },
    "knowledge_base": {
        "collections": [
            {
                "collection_id": "hr-policies",
                "source_type": "vector_db",
                "chunk_strategy": "semantic_paragraph",
                "description": "Employee handbook, leave policy, sick pay",
            }
        ]
    },
    "evaluation_rules": {
        "mandatory_checks": [],
        "scoring_criteria": [],
        "response_mode": "direct_answer",
        "ambiguity_handling": {
            "confidence_threshold_for_review": 0.80,
            "low_confidence_message": (
                "I cannot find a definitive policy answer. "
                "Please contact HR directly."
            ),
        },
    },
    "governance": {
        "approval_tiers": [],
        "audit_requirements": {
            "citation_required": True,
        },
    },
    "agent_behaviour": {
        "llm": {"temperature": 0.0},
        "tone": "conversational",
    },
    "output": {
        "formats": [{"type": "json"}],
    },
}

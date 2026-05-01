# BACKLOG

# Items noticed during this conversation that belong in future development.

# Do not build any of these during Skills 01-06.

# Review before starting work after first customer is live.

---

## OPEN ITEMS — Prioritised

| Date    | What                                                                                             | Relevant to                          | Priority | Notes                                                                                                          |
| ------- | ------------------------------------------------------------------------------------------------ | ------------------------------------ | -------- | -------------------------------------------------------------------------------------------------------------- |
| 2026-04 | Self-consistency voting — run same compliance check 3 times, take majority                       | After SK04                           | High     | Reduces hallucination risk on borderline decisions. Only for checks above approval threshold.                  |
| 2026-04 | Verification step — second LLM call after synthesis checks every claim against retrieved context | After SK05                           | High     | Catches hallucinations before PDF report. Add as optional guardrail node.                                      |
| 2026-04 | Human feedback capture — when evaluator overrides AI score, capture correction                   | After first customer                 | High     | Requires a feedback UI in the frontend. Corrections flow back into few-shot examples.                          |
| 2026-04 | Score drift detection in production — alert when average confidence drops week-over-week         | After SK05                           | High     | LangSmith has the data. Needs a monitoring rule and Slack alert.                                               |
| 2026-04 | Prompt versioning — track which prompt version produced which result                             | After SK04                           | Medium   | Cannot identify cause of accuracy changes without this. Store prompt_version in decisions table.               |
| 2026-04 | Pydantic validation on synthesizer output                                                        | After SK03b                          | Medium   | ComplianceCheckResult and ScoringCriterionResult are done. SynthesisResult needed.                             |
| 2026-04 | OCR for scanned PDFs — Tesseract integration                                                     | After first customer                 | Medium   | pypdf returns empty text for scanned documents. Many real vendor submissions are scanned.                      |
| 2026-04 | Document versioning — track what was evaluated at what version                                   | After SK05                           | Medium   | Resubmission currently deletes all previous data. Needed for audit trail completeness.                         |
| 2026-04 | Confidence calibration — empirical calibration of GPT-4o confidence scores                       | After first customer                 | Medium   | Requires ground truth dataset. 0.8 confidence may not mean 80% accurate on your documents.                     |
| 2026-04 | Context compression — extract only relevant sentences from chunks before sending to LLM          | After SK03b                          | Medium   | LangChain ContextualCompressionRetriever. Reduces noise in context window.                                     |
| 2026-04 | Lost-in-the-middle handling — place most important chunks first and last                         | After SK03b                          | Medium   | LLMs attend less to content in middle of long context. Sort chunks by importance.                              |
| 2026-04 | Contextual chunk headers — prepend each chunk with parent section summary                        | After SK03b                          | Low      | Gives LLM context of where chunk sits in document. Additional LLM call per chunk.                              |
| 2026-04 | A/B testing prompts — run two prompt versions on same evaluation, compare accuracy               | After first customer                 | Low      | Requires evaluation dataset for comparison. Cannot do this without ground truth.                               |
| 2026-04 | Evaluation ground truth dataset — collect correct evaluations for accuracy measurement           | After first customer                 | Low      | Need real customer data to build this. Ask first customer to manually evaluate 20 vendors as ground truth.     |
| 2026-04 | Chunk overlap strategy — sentence-boundary overlap instead of fixed token overlap                | After SK03b if score not good enough | Low      | Only needed if retrieval quality test still fails specific boundary cases.                                     |
| 2026-04 | Retrieval quality monitoring in production                                                       | After SK05                           | Low      | 80% threshold test runs in dev. Need scheduled job that runs same test on production collections weekly.       |
| 2026-04 | Hierarchical chunking — summary chunk + detail chunks per section                                | After SK03b if needed                | Low      | Higher complexity. Only add if standard chunking still struggles with very long sections.                      |
| 2026-04 | SaaS billing system — usage metering per org                                                     | After SK06                           | Low      | Current platform has no billing. Need Stripe integration and usage tracking before selling to second customer. |
| 2026-04 | Executive dashboard — CEO/CFO view of all active evaluations                                     | After SK06                           | Low      | Described in the platform vision. Not needed until multiple departments active at one company.                 |
| 2026-04 | Approval SLA checker background job — flags overdue approvals                                    | After SK05                           | Low      | Modal scheduled function that runs hourly. Sends Slack reminder when approval is overdue.                      |

---

## COMPLETED ITEMS

| Date | What was built | Built in skill | Notes |
| ---- | -------------- | -------------- | ----- |
|      |                |                |       |

---

## REJECTED ITEMS

| Date    | What was considered            | Reason rejected                                                                                                                  |
| ------- | ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| 2026-04 | Fine-tuning models             | Too expensive and slow for v1. Few-shot prompting achieves comparable results on this use case. Revisit after 1000+ evaluations. |
| 2026-04 | Image/audio document ingestion | Out of scope for RFP evaluation. Vendor responses are text documents.                                                            |
| 2026-04 | Multi-language support         | English only for v1. Add after first non-English customer requests it.                                                           |

## BACKLOG ITEM: Vendor Q&A — Conversational RAG for Decision Makers

**Priority:** High
**Build in:** Skill 07 (Output + Frontend) — after Retrieval Agent (Skill 03b) complete
**Depends on:** Qdrant collections populated by Ingestion Agent, Retrieval Agent working

---

### What this is

A conversational Q&A interface on the Evaluation Report page (Page 8) where a
decision-maker can ask free-form questions about any vendor's submitted documents
after the evaluation has run. Answers are grounded in the vendor's actual text —
not the system's structured extraction — so the decision-maker can read the
vendor's own words before making a judgment.

This is the simplest possible RAG in the system. The vendor documents are already
in Qdrant from the Ingestion Agent. The Retrieval Agent already searches them.
This feature just exposes that capability through a chat interface.

---

### Why it exists — the problem it solves

Right now the decision-maker sees a rejection and either accepts it or overrides it
blind. They are trusting the system's extraction without being able to interrogate
the source documents themselves.

Example scenario:
The system rejects Vendor X for insufficient client references.
The CFO asks: "Can you show me their references and how big those clients are?"
Without this feature: the CFO cannot ask. They accept the rejection or override
it with no evidence.
With this feature: the CFO reads the vendor's own words. Three NHS Trust clients,
500+ users each, named on page 12 of their submission. The CFO overrides with
genuine informed judgment and a defensible audit trail.

---

### Design decisions — already made, do not revisit

1. SCOPE: User selects one vendor from a dropdown. Q&A is scoped to that vendor's
   Qdrant collection only. No cross-vendor answers. Prevents confusion.

2. LOCATION: Tab on the Evaluation Report page (Page 8) — "Ask about this vendor"
   tab alongside the existing results. Most natural moment is when reviewing results.

3. OVERRIDE CONNECTION: After the user gets an answer, they can click
   "Override rejection using this evidence." The override form pre-fills with the
   relevant grounding quote from the Q&A answer as the justification. The audit
   trail then contains actual vendor document evidence, not just a human opinion.

4. STRICT GROUNDING: Every answer must cite the exact quote and page number from
   the vendor document. If the document does not contain the answer, the system
   says "I could not find information about this in the vendor's submission."
   Never hallucinate supporting evidence for an override. This protects the
   audit trail.

5. NOT A GENERAL CHATBOT: Only answers questions about vendor documents in the
   current evaluation. Does not answer general knowledge questions. Out-of-scope
   questions get: "I can only answer questions about the vendor documents in this
   evaluation."

---

### What to build

BACKEND — one new FastAPI endpoint:

POST /api/evaluations/{run_id}/vendors/{vendor_id}/ask

Request body:
question: str — the user's free-form question
org_id: str — for tenant isolation

What it does: 1. Validates the run_id and vendor_id belong to the org_id (tenant check) 2. Calls Retrieval Agent with the question, scoped to vendor_id collection 3. Passes retrieved chunks to LLM with a strict grounding prompt 4. Returns answer with cited chunks

Response:
answer: str — plain English answer
citations: List[Citation] — grounding quotes with page numbers
vendor_id: str
confidence: str — "high" | "medium" | "low"
not_found: bool — True if document did not contain answer

New Pydantic models needed (add to output_models.py in Skill 07):

    class Citation(BaseModel):
        quote: str
        page_number: int
        section_title: str
        chunk_id: str

    class VendorQARequest(BaseModel):
        question: str
        org_id: str

    class VendorQAResponse(BaseModel):
        answer: str
        citations: List[Citation]
        vendor_id: str
        confidence: str
        not_found: bool
        question_echo: str         — echo back the question asked

FRONTEND — new panel on Page 8 (Evaluation Report):

Tab: "Ask about this vendor" alongside existing report tabs.

Left side: vendor selector dropdown (shows all vendors in the evaluation,
rejected vendors shown with red indicator, passed vendors with teal).

Main area: chat-style interface.
Input box at bottom: "Ask a question about this vendor's submission..."
Answers appear above with: - Plain English answer - Grounding quotes in styled blockquote boxes (same style as Page 6
compliance results — dark background, indigo left border) - Page number and section title for each quote - Confidence indicator

Override connection:
When vendor is rejected and Q&A returns an answer with citations,
show a button below the answer:
"Override rejection — use this as justification"
Clicking this: - Opens the override side panel (same as Page 10 override panel) - Pre-fills the reason field with the most relevant citation quote - User can edit before submitting - Override is saved with the grounding evidence as documented reason

Empty state: "Select a vendor and ask a question about their submission.
For example: 'What client references did they provide?' or
'What did they say about their security approach?'"

LLM PROMPT for the Q&A endpoint (strict grounding):

System: "You are answering questions about a vendor's submitted document.
Answer only using the provided context. Every claim in your answer must
reference a specific passage from the context. If the context does not
contain the answer, say exactly: 'I could not find information about this
in the vendor's submission.' Do not use any knowledge outside the provided
context. Do not speculate."

User: "Context: {retrieved_chunks_with_page_numbers}
Question: {user_question}
Answer with citations to specific passages."

---

### What does NOT change

- No new agents
- No new databases
- No new Qdrant collections (vendor documents already there from Ingestion)
- No changes to the evaluation pipeline
- No changes to existing output models except adding Citation,
  VendorQARequest, VendorQAResponse in Skill 07

---

### Test case — use Chemtura / YASH

When this is built, test with:
Question: "What client references did YASH provide and how large are those clients?"
Expected: System finds the John Deere, Stanley Works, Monsanto references
from the YASH document and shows the exact text with page numbers.

Question: "What did YASH say about their insurance coverage?"
Expected: not_found=True because YASH left an internal question in their
submission instead of answering. System says it could not find information.
This is the correct answer — do not hallucinate insurance coverage.

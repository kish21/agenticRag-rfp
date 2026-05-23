export const AGENTS = [
  "planner", "ingestion", "retrieval", "extraction",
  "evaluation", "comparator", "decision", "explanation", "critic",
] as const;

export const AGENT_LABELS: Record<string, string> = {
  planner:    "Planner",
  ingestion:  "Ingestion",
  retrieval:  "Retrieval",
  extraction: "Extraction",
  evaluation: "Evaluation",
  comparator: "Comparator",
  decision:   "Decision",
  explanation:"Explanation",
  critic:     "Critic",
};

export const ROLE_DISPLAY: Record<string, string> = {
  procurement_manager: "Procurement",
  executive:           "Executive",
  org_admin:           "Admin",
};

export const STATUS_DOT: Record<string, string> = {
  complete:    "var(--color-success)",
  completed:   "var(--color-success)",
  running:     "var(--color-info)",
  pending:     "var(--color-warning)",
  failed:      "var(--color-error)",
  interrupted: "var(--color-warning)",
  draft:       "var(--color-text-muted)",
  done:        "var(--color-success)",
  blocked:     "var(--color-error)",
};

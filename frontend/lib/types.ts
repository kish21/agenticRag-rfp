export interface EvalRun {
  run_id: string;
  rfp_title: string;
  status: string;
  vendor_count: number;
  created_at: string;
  started_at?: string;
  total_cost_usd?: number | null;
  currency?: string;
}

export interface AgentEvent {
  agent: string;
  status: "pending" | "running" | "done" | "blocked" | "interrupted" | "failed" | "completed" | "complete";
  message: string;
}

export interface VendorScore {
  vendor_name: string;
  decision: string;
  total_score: number;
  score_confidence?: number | null;
  recommendation?: string | null;
  summary?: string;
}

export interface EvalResults {
  status?: string;
  recommendation?: string;
  approval_tier?: string;
  decision_confidence?: number | null;
  requires_human_review?: boolean;
  review_reasons?: string[];
  vendors?: VendorScore[];
  agent_log?: { message?: string; log_msg?: string }[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  suggestedCriteria?: string[];
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: string;
  updatedAt: string;
}

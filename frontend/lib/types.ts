export interface EvalRun {
  run_id: string;
  rfp_title: string;
  status: string;
  vendor_count: number;
  created_at: string;
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
  summary?: string;
}

export interface EvalResults {
  recommendation?: string;
  approval_tier?: string;
  vendors?: VendorScore[];
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

export type SourceKey = "org" | "dept" | "user" | "rfp";

export interface MandatoryCheck {
  check_id: string;
  name: string;
  description: string;
  what_passes: string;
  extraction_target_id: string;
  source: string;
  is_locked: boolean;
}

export interface ScoringCriterion {
  criterion_id: string;
  name: string;
  weight: number;
  description?: string;
  rubric_9_10?: string;
  rubric_6_8?: string;
  rubric_3_5?: string;
  rubric_0_2?: string;
  extraction_target_ids?: string[];
  source: string;
  is_locked: boolean;
}

export interface EvaluationSetup {
  mandatory_checks: MandatoryCheck[];
  scoring_criteria: ScoringCriterion[];
  total_weight: number;
  source: string;
  currency?: string;
  contract_value?: number | null;
  vendor_count?: number;
  rfp_title?: string;
  department?: string;
}

export interface DupPair {
  a: { name: string; source: SourceKey };
  b: { name: string; source: SourceKey };
  idA: string;
  idB: string;
}

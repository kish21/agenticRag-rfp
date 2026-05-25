import type { SourceKey, EvaluationSetup, DupPair } from "./types";

export { type DupPair };

export function round3(n: number): number {
  return Math.round(n * 1000) / 1000;
}

export function genId(source: SourceKey, type: "mandatory" | "scoring"): string {
  const prefix = type === "mandatory" ? "MC" : "SC";
  const rand = Math.random().toString(36).slice(2, 10).toUpperCase();
  return `${prefix}-${source.toUpperCase()}-${rand}`;
}

export function normName(n: string): string {
  return n.toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
}

export function isNearDup(a: string, b: string): boolean {
  const wa = normName(a).split(" ").filter(Boolean);
  const wb = normName(b).split(" ").filter(Boolean);
  if (wa.length < 3 || wb.length < 3) return false;
  const wbStr = wb.join(" ");
  for (let i = 0; i <= wa.length - 3; i++) {
    if (wbStr.includes(wa.slice(i, i + 3).join(" "))) return true;
  }
  return false;
}

export function findDupPairs(setup: EvaluationSetup): DupPair[] {
  const all: Array<{ name: string; source: SourceKey; id: string }> = [
    ...setup.mandatory_checks.map(c => ({ name: c.name, source: c.source as SourceKey, id: c.check_id })),
    ...setup.scoring_criteria.map(c => ({ name: c.name, source: c.source as SourceKey, id: c.criterion_id })),
  ];
  const pairs: DupPair[] = [];
  for (let i = 0; i < all.length; i++) {
    for (let j = i + 1; j < all.length; j++) {
      if (all[i].source !== all[j].source && isNearDup(all[i].name, all[j].name)) {
        pairs.push({ a: all[i], b: all[j], idA: all[i].id, idB: all[j].id });
      }
    }
  }
  return pairs;
}

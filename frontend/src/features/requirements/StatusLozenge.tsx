import type { RequirementStatus } from "../../types/requirement";
import { statusMeta } from "./constants";

export function StatusLozenge({ status }: { status: RequirementStatus }) {
  const meta = statusMeta[status];
  return <span className={`status-lozenge status-${meta.tone}`}>{meta.label}</span>;
}


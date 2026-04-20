export type RequirementStatus = "backlog" | "approved" | "in_progress" | "done" | "rejected";

export interface Requirement {
  id: string;
  req_id: string;
  title: string;
  description: string;
  status: RequirementStatus;
  vote_count: number;
  creator_name: string;
  creator_open_id: string;
  created_at: string;
  updated_at: string;
}

export interface RequirementListResponse {
  items: Requirement[];
}

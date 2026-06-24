export type RequirementStatus = "backlog" | "approved" | "in_progress" | "done" | "rejected";
export interface CurrentUser {
  id: string;
  name: string;
}

export interface RequirementTag {
  id: string;
  name: string;
  slug: string;
  color: string;
}

export interface Requirement {
  id: string;
  req_id: string;
  title: string;
  description: string;
  status: RequirementStatus;
  vote_count: number;
  has_voted: boolean;
  creator_name: string;
  creator_open_id: string;
  tags: RequirementTag[];
  linked_task?: {
    id: string;
    number: number;
    title: string;
    status: string;
  } | null;
  created_at: string;
  updated_at: string;
}

export interface RequirementListResponse {
  items: Requirement[];
}

export interface SimilarRequirement {
  id: string;
  number: number;
  title: string;
  description: string;
  status: string;
  votes_count: number;
  similarity: number;
  is_high_confidence: boolean;
  reason?: string | null;
}

export interface SimilarRequirementsResponse {
  items: SimilarRequirement[];
  ai_enhanced: boolean;
}

export type RequirementStatus = "backlog" | "approved" | "in_progress" | "done" | "rejected";
export type UserRole = "visitor" | "admin";

export interface CurrentUser {
  id: string;
  name: string;
  role: UserRole;
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

export interface CommentItem {
  id: string;
  requirement_id: string;
  author_name: string;
  body: string;
  created_at: string;
}

export interface CommentListResponse {
  items: CommentItem[];
}

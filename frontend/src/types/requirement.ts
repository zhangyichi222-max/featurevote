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
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
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

export interface RequirementSourceMessage {
  message_id: string;
  chat_id: string;
  chat_name: string;
  sender_open_id?: string | null;
  sender_name?: string | null;
  sent_at?: string | null;
  root_id?: string | null;
  parent_id?: string | null;
  raw_text: string;
  is_direct_source: boolean;
}

export interface RequirementSourceGroup {
  key: string;
  kind: "thread" | "window";
  chat_id: string;
  chat_name: string;
  messages: RequirementSourceMessage[];
}

export interface RequirementSourcesResponse {
  groups: RequirementSourceGroup[];
}

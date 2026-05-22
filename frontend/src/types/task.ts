import type { CurrentUser } from "./requirement";

export type TaskStatus = "todo" | "in_progress" | "blocked" | "done" | "canceled";

export interface TaskLabel {
  id: string;
  name: string;
  slug: string;
  color: string;
}

export interface TaskItem {
  id: string;
  number: number;
  title: string;
  description_markdown: string;
  status: TaskStatus;
  assignee: CurrentUser | null;
  created_by: CurrentUser;
  updated_by?: CurrentUser | null;
  source_post?: {
    id: string;
    number: number;
    title: string;
    status: string;
  } | null;
  labels: TaskLabel[];
  created_at: string;
  updated_at: string;
}

export interface TaskListResponse {
  items: TaskItem[];
}

export interface TaskLabelListResponse {
  items: TaskLabel[];
}

export interface TaskAssigneeListResponse {
  items: CurrentUser[];
}

export interface TaskPayload {
  title: string;
  description_markdown: string;
  status: TaskStatus;
  assignee_user_id: string | null;
  labels: string[];
}

export interface FeishuMessageEvidence {
  conversation_id: string;
  conversation_title: string;
  message_id: string;
  sender_name: string;
  created_at: string;
  content: string;
}

export interface FeishuTaskCandidate {
  candidate_id: string;
  title: string;
  description_markdown: string;
  evidence: FeishuMessageEvidence[];
  duplicate_hints: Array<{
    id: string;
    number: number;
    title: string;
    status: string;
  }>;
}

export interface FeishuTaskImportPreviewResponse {
  candidates: FeishuTaskCandidate[];
  conversations_count: number;
  messages_count: number;
  skipped_messages_count: number;
}

export interface FeishuTaskImportCreateResponse {
  items: TaskItem[];
}

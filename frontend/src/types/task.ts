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

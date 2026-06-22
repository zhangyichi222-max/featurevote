import { apiClient } from "../../api/client";
import type {
  TaskAssigneeListResponse,
  TaskItem,
  TaskLabelListResponse,
  TaskListResponse,
  TaskPayload,
  TaskStatus,
} from "../../types/task";

export async function fetchTasks(filters: {
  query?: string;
  status?: TaskStatus | "all";
  assigneeId?: string;
  label?: string;
} = {}) {
  const params = new URLSearchParams();
  if (filters.query) {
    params.set("query", filters.query);
  }
  if (filters.status && filters.status !== "all") {
    params.append("statuses", filters.status);
  }
  if (filters.assigneeId) {
    params.set("assignee_id", filters.assigneeId);
  }
  if (filters.label) {
    params.append("labels", filters.label);
  }
  const query = params.toString();
  return apiClient.get<TaskListResponse>(`/tasks${query ? `?${query}` : ""}`);
}

export async function createTask(payload: TaskPayload) {
  return apiClient.post<TaskItem>("/tasks", payload);
}

export async function updateTask(taskId: string, payload: Partial<TaskPayload>) {
  return apiClient.patch<TaskItem>(`/tasks/${taskId}`, payload);
}

export async function deleteTask(taskId: string) {
  return apiClient.delete<{ success: boolean; message: string }>(`/tasks/${taskId}`);
}

export async function fetchTaskLabels() {
  return apiClient.get<TaskLabelListResponse>("/task-labels");
}

export async function createTaskLabel(payload: { name: string; color: string }) {
  return apiClient.post<TaskLabelListResponse>("/task-labels", payload);
}

export async function deleteTaskLabel(labelId: string) {
  return apiClient.delete<{ success: boolean; message: string }>(`/task-labels/${labelId}`);
}

export async function fetchTaskAssignees() {
  return apiClient.get<TaskAssigneeListResponse>("/tasks/assignees");
}

export async function uploadTaskImage(file: File) {
  return apiClient.upload<{ url: string }>("/task-assets/images", file);
}


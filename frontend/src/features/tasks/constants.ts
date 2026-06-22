import type { TaskStatus } from "../../types/task";

export const statusLabels: Record<TaskStatus, string> = {
  todo: "待处理",
  in_progress: "进行中",
  blocked: "阻塞",
  done: "完成",
  canceled: "取消",
};

export const statuses: Array<TaskStatus | "all"> = ["all", "todo", "in_progress", "blocked", "done", "canceled"];
export const labelColors = ["#2f75d6", "#1f8a5b", "#b83245", "#8f5bd6", "#d68b2f"];

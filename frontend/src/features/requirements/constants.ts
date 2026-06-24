import type { RequirementStatus } from "../../types/requirement";

export type SortMode = "popular" | "newest" | "recent";
export type StatusFilter = "all" | RequirementStatus;
export type AppView = "requirements" | "tasks";

export const statusMeta: Record<
  RequirementStatus,
  {
    label: string;
    tone: string;
    response: string;
  }
> = {
  backlog: {
    label: "待评估",
    tone: "neutral",
    response: "这份需求草稿正在收集投票和反馈，等待评估。",
  },
  approved: {
    label: "已采纳",
    tone: "info",
    response: "这份需求草稿已被采纳，等待创建正式任务。",
  },
  in_progress: {
    label: "已转任务",
    tone: "warning",
    response: "这份需求草稿已转为正式任务，请在任务管理中跟踪进度。",
  },
  done: {
    label: "任务已完成",
    tone: "success",
    response: "关联任务已完成，这份需求草稿保留用于追溯。",
  },
  rejected: {
    label: "未采纳",
    tone: "danger",
    response: "这份需求草稿当前未被采纳。",
  },
};

export const statusOrder: RequirementStatus[] = ["backlog", "approved", "in_progress", "done", "rejected"];

export const filterOptions: Array<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "backlog", label: "待评估" },
  { value: "approved", label: "已采纳" },
  { value: "in_progress", label: "已转任务" },
  { value: "done", label: "任务已完成" },
  { value: "rejected", label: "未采纳" },
];
export const tagColors = ["#2f75d6", "#1f8a5b", "#b83245", "#8f5bd6", "#d68b2f"];

export type ComposerField = "title" | "description";
export type ComposerStep = "idea" | "draft";

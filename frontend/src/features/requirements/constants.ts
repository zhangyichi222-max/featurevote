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
    label: "待收集",
    tone: "neutral",
    response: "这个建议正在收集投票和讨论。",
  },
  approved: {
    label: "已计划",
    tone: "info",
    response: "这个建议已有足够反馈，已进入规划。",
  },
  in_progress: {
    label: "进行中",
    tone: "warning",
    response: "团队正在处理这个建议。",
  },
  done: {
    label: "已完成",
    tone: "success",
    response: "这个建议已经上线或解决。",
  },
  rejected: {
    label: "暂不采纳",
    tone: "danger",
    response: "这个建议暂不符合当前产品方向。",
  },
};

export const statusOrder: RequirementStatus[] = ["backlog", "approved", "in_progress", "done", "rejected"];

export const filterOptions: Array<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "backlog", label: "待收集" },
  { value: "approved", label: "已计划" },
  { value: "in_progress", label: "进行中" },
  { value: "done", label: "已完成" },
  { value: "rejected", label: "暂不采纳" },
];
export const tagColors = ["#2f75d6", "#1f8a5b", "#b83245", "#8f5bd6", "#d68b2f"];

export type ComposerField = "title" | "description";
export type ComposerStep = "idea" | "draft";

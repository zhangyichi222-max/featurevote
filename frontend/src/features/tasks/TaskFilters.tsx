import type { CurrentUser } from "../../types/requirement";
import type { TaskLabel, TaskStatus } from "../../types/task";
import { statusLabels, statuses } from "./constants";

export function TaskFilters({
  query,
  status,
  assigneeId,
  label,
  labels,
  assignees,
  counts,
  onQueryChange,
  onStatusChange,
  onAssigneeChange,
  onLabelChange,
}: {
  query: string;
  status: TaskStatus | "all";
  assigneeId: string;
  label: string;
  labels: TaskLabel[];
  assignees: CurrentUser[];
  counts: Record<string, number>;
  onQueryChange: (value: string) => void;
  onStatusChange: (value: TaskStatus | "all") => void;
  onAssigneeChange: (value: string) => void;
  onLabelChange: (value: string) => void;
}) {
  return (
    <div className="task-filters">
      <input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="搜索任务" />
      <select value={status} onChange={(event) => onStatusChange(event.target.value as TaskStatus | "all")}>
        {statuses.map((item) => (
          <option key={item} value={item}>
            {item === "all" ? "全部状态" : statusLabels[item]} {item !== "all" && counts[item] ? "(" + counts[item] + ")" : ""}
          </option>
        ))}
      </select>
      <select value={assigneeId} onChange={(event) => onAssigneeChange(event.target.value)}>
        <option value="">全部负责人</option>
        {assignees.map((user) => (
          <option key={user.id} value={user.id}>{user.name}</option>
        ))}
      </select>
      <select value={label} onChange={(event) => onLabelChange(event.target.value)}>
        <option value="">全部标签</option>
        {labels.map((item) => (
          <option key={item.id} value={item.slug}>{item.name}</option>
        ))}
      </select>
    </div>
  );
}

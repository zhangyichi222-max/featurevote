import type { TaskItem } from "../../types/task";
import { statusLabels } from "./constants";

export function TaskList({
  tasks,
  selectedTask,
  page,
  pageSize,
  total,
  totalPages,
  onPageChange,
  onSelect,
}: {
  tasks: TaskItem[];
  selectedTask: TaskItem | null;
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  onSelect: (task: TaskItem) => void;
}) {
  return (
    <div className="task-main-pane">
      <div className="task-list-header">
        <span>状态</span>
        <span>任务</span>
        <span>负责人</span>
        <span>标签</span>
      </div>
      <div className="task-list">
        {tasks.map((task) => (
          <button
            key={task.id}
            className={`task-row ${selectedTask?.id === task.id ? "selected" : ""}`}
            type="button"
            onClick={() => onSelect(task)}
          >
            <span className={`task-status status-${task.status}`}>{statusLabels[task.status]}</span>
            <span className="task-title-cell">
              <strong>TASK-{task.number}</strong>
              <span>{task.title}</span>
            </span>
            <span className="task-assignee-cell">{task.assignee?.name ?? "未分配"}</span>
            <span className="task-labels">
              {task.labels.map((item) => (
                <small key={item.id} style={{ borderColor: item.color }}>
                  <span className="label-dot" style={{ backgroundColor: item.color }} />
                  {item.name}
                </small>
              ))}
            </span>
          </button>
        ))}
        {!tasks.length ? <div className="task-empty">暂无任务。</div> : null}
      </div>
      <TaskPagination
        page={page}
        pageSize={pageSize}
        total={total}
        totalPages={totalPages}
        onPageChange={onPageChange}
      />
    </div>
  );
}

function TaskPagination({
  page,
  pageSize,
  total,
  totalPages,
  onPageChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  if (!total) {
    return null;
  }
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  const pageItems = paginationItems(page, totalPages);
  return (
    <div className="task-pagination">
      <span>第 {start}–{end} 条，共 {total} 条</span>
      <div className="task-pagination-actions">
        <button type="button" onClick={() => onPageChange(page - 1)} disabled={page <= 1}>上一页</button>
        {pageItems.map((item) =>
          typeof item === "number" ? (
            <button
              key={item}
              className={item === page ? "active" : ""}
              type="button"
              onClick={() => onPageChange(item)}
              aria-current={item === page ? "page" : undefined}
            >
              {item}
            </button>
          ) : <span key={item}>…</span>,
        )}
        <button type="button" onClick={() => onPageChange(page + 1)} disabled={page >= totalPages}>下一页</button>
      </div>
    </div>
  );
}

function paginationItems(page: number, totalPages: number): Array<number | string> {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }
  const items: Array<number | string> = [1];
  if (page > 4) items.push("left-ellipsis");
  const start = Math.max(2, page - 1);
  const end = Math.min(totalPages - 1, page + 1);
  for (let current = start; current <= end; current += 1) items.push(current);
  if (page < totalPages - 3) items.push("right-ellipsis");
  items.push(totalPages);
  return items;
}

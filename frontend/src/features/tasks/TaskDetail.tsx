import { RichContentPreview } from "../rich-content/RichContentEditor";
import type { CurrentUser } from "../../types/requirement";
import type { TaskItem, TaskStatus } from "../../types/task";
import { statusLabels, statuses } from "./constants";

export function TaskDetail({
  task,
  currentUser,
  isBusy,
  onEdit,
  onStatusChange,
  onDelete,
}: {
  task: TaskItem | null;
  currentUser: CurrentUser;
  isBusy: boolean;
  onEdit: (task: TaskItem) => void;
  onStatusChange: (task: TaskItem, status: TaskStatus) => Promise<void>;
  onDelete: (task: TaskItem) => Promise<void>;
}) {
  if (!task) {
    return (
      <aside className="task-detail task-detail-empty">
        <h3>任务详情</h3>
        <p>选择一个任务查看详情。</p>
      </aside>
    );
  }
  const canEdit = currentUser.role === "admin" || task.assignee?.id === currentUser.id;
  const canDelete = currentUser.role === "admin";
  return (
    <aside className="task-detail">
      <div className="task-detail-header">
        <div>
          <span className="task-detail-key">TASK-{task.number}</span>
          <h3>{task.title}</h3>
        </div>
        {canEdit ? <button className="secondary-button" type="button" onClick={() => onEdit(task)}>编辑</button> : null}
      </div>
      {canDelete ? (
        <div className="task-detail-actions">
          <button className="danger-button" type="button" onClick={() => onDelete(task)} disabled={isBusy}>
            删除
          </button>
        </div>
      ) : null}
      <div className="task-properties">
        <div className="task-property-row">
          <span>状态</span>
          {canEdit ? (
            <select value={task.status} onChange={(event) => onStatusChange(task, event.target.value as TaskStatus)} disabled={isBusy}>
              {statuses.filter((item): item is TaskStatus => item !== "all").map((item) => (
                <option key={item} value={item}>{statusLabels[item]}</option>
              ))}
            </select>
          ) : (
            <strong className={`task-status status-${task.status}`}>{statusLabels[task.status]}</strong>
          )}
        </div>
        <div className="task-property-row">
          <span>负责人</span>
          <strong>{task.assignee?.name ?? "未分配"}</strong>
        </div>
        <div className="task-property-row">
          <span>创建人</span>
          <strong>{task.created_by.name}</strong>
        </div>
        <div className="task-property-row task-property-labels">
          <span>标签</span>
          <div className="task-labels detail-labels">
            {task.labels.length ? task.labels.map((item) => (
              <small key={item.id} style={{ borderColor: item.color }}>
                <span className="label-dot" style={{ backgroundColor: item.color }} />
                {item.name}
              </small>
            )) : <em>无</em>}
          </div>
        </div>
      </div>
      <section className="task-description-panel">
        <h4>描述</h4>
        <RichContentPreview markdown={task.description_markdown || "暂无描述。"} />
      </section>
    </aside>
  );
}



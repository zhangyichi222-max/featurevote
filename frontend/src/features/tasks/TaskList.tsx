import type { TaskItem } from "../../types/task";
import { statusLabels } from "./constants";

export function TaskList({ tasks, selectedTask, onSelect }: { tasks: TaskItem[]; selectedTask: TaskItem | null; onSelect: (task: TaskItem) => void }) {
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
    </div>
  );
}

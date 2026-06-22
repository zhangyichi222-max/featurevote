export function TaskToolbar({ isAdmin, onNewTask }: { isAdmin: boolean; onNewTask: () => void }) {
  return (
    <div className="task-toolbar">
      <div>
        <p className="eyebrow">任务管理</p>
        <h2>开发任务</h2>
      </div>
      {isAdmin ? (
        <div className="task-toolbar-actions">
          <button className="primary-button" type="button" onClick={onNewTask}>
            新建任务
          </button>
        </div>
      ) : null}
    </div>
  );
}

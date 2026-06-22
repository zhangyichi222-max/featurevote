import { useEffect, useMemo, useState } from "react";

import type { CurrentUser } from "../../types/requirement";
import type { TaskItem, TaskLabel, TaskPayload, TaskStatus } from "../../types/task";
import {
  createTask,
  createTaskLabel,
  deleteTask,
  deleteTaskLabel,
  fetchTaskAssignees,
  fetchTaskLabels,
  fetchTasks,
  updateTask,
} from "./api";
import { labelColors } from "./constants";
import { TaskDetail } from "./TaskDetail";
import { TaskEditor } from "./TaskEditor";
import { TaskFilters } from "./TaskFilters";
import { TaskList } from "./TaskList";
import { TaskToolbar } from "./TaskToolbar";

export function TaskPage({ currentUser }: { currentUser: CurrentUser | null }) {
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [labels, setLabels] = useState<TaskLabel[]>([]);
  const [assignees, setAssignees] = useState<CurrentUser[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<TaskStatus | "all">("all");
  const [assigneeId, setAssigneeId] = useState("");
  const [label, setLabel] = useState("");
  const [selectedTask, setSelectedTask] = useState<TaskItem | null>(null);
  const [editingTask, setEditingTask] = useState<TaskItem | null>(null);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  const isAdmin = currentUser?.role === "admin";

  async function loadTasks() {
    const data = await fetchTasks({ query, status, assigneeId, label });
    setTasks(data.items);
    setLabels((current) => mergeTaskLabels(current, data.items));
    setAssignees((current) => mergeTaskAssignees(current, data.items));
    setSelectedTask((current) => {
      const targetId = new URLSearchParams(window.location.search).get("task");
      if (targetId) {
        return data.items.find((item) => item.id === targetId) ?? null;
      }
      return current ? data.items.find((item) => item.id === current.id) ?? null : current;
    });
  }

  async function loadMeta() {
    const [labelResult, assigneeResult] = await Promise.allSettled([fetchTaskLabels(), fetchTaskAssignees()]);
    if (labelResult.status === "fulfilled") {
      setLabels(labelResult.value.items);
    }
    if (assigneeResult.status === "fulfilled") {
      setAssignees(assigneeResult.value.items);
    }
    if (labelResult.status === "rejected" && assigneeResult.status === "rejected") {
      throw labelResult.reason instanceof Error ? labelResult.reason : new Error("任务元数据加载失败。");
    }
  }

  useEffect(() => {
    loadMeta().catch((error: Error) => setNotice(error.message));
  }, []);

  useEffect(() => {
    loadTasks().catch((error: Error) => setNotice(error.message));
  }, [assigneeId, label, query, status]);

  const counts = useMemo(() => {
    return tasks.reduce<Record<string, number>>((result, task) => {
      result[task.status] = (result[task.status] ?? 0) + 1;
      return result;
    }, {});
  }, [tasks]);

  async function handleSave(payload: TaskPayload) {
    setIsBusy(true);
    try {
      if (editingTask) {
        await updateTask(
          editingTask.id,
          isAdmin
            ? payload
            : {
                description_markdown: payload.description_markdown,
                status: payload.status,
              },
        );
        setNotice("任务已更新。");
      } else {
        await createTask(payload);
        setNotice("任务已创建。");
      }
      setIsEditorOpen(false);
      setEditingTask(null);
      await loadTasks();
      await loadMeta();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "任务保存失败。");
      throw error;
    } finally {
      setIsBusy(false);
    }
  }

  async function handleQuickStatus(task: TaskItem, nextStatus: TaskStatus) {
    setIsBusy(true);
    try {
      await updateTask(task.id, { status: nextStatus });
      await loadTasks();
      setNotice("状态已更新。");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "状态更新失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleDeleteTask(task: TaskItem) {
    if (!isAdmin) {
      setNotice("只有管理员可以删除任务。");
      return;
    }
    const sourceMessage = task.source_post ? "，并同步删除关联需求" : "";
    if (!window.confirm(`确定删除 TASK-${task.number}${sourceMessage}吗？`)) {
      return;
    }
    setIsBusy(true);
    try {
      await deleteTask(task.id);
      const params = new URLSearchParams(window.location.search);
      if (params.get("task") === task.id) {
        params.delete("task");
        window.history.replaceState(null, "", `${window.location.pathname}${params.toString() ? `?${params.toString()}` : ""}`);
      }
      setSelectedTask(null);
      await loadTasks();
      setNotice(task.source_post ? "任务已删除，关联需求已同步删除。" : "任务已删除。");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "任务删除失败。");
    } finally {
      setIsBusy(false);
    }
  }

  if (!currentUser) {
    return <div className="task-empty">请先登录后查看任务管理。</div>;
  }

  return (
    <section className="task-page">
      {notice ? <div className="task-notice">{notice}</div> : null}
      <TaskToolbar isAdmin={isAdmin} onNewTask={() => setIsEditorOpen(true)} />

      <TaskFilters
        query={query}
        status={status}
        assigneeId={assigneeId}
        label={label}
        labels={labels}
        assignees={assignees}
        counts={counts}
        onQueryChange={setQuery}
        onStatusChange={setStatus}
        onAssigneeChange={setAssigneeId}
        onLabelChange={setLabel}
      />

      <div className="task-layout">
        <TaskList tasks={tasks} selectedTask={selectedTask} onSelect={setSelectedTask} />

        <TaskDetail
          task={selectedTask}
          currentUser={currentUser}
          isBusy={isBusy}
          onEdit={(task) => {
            setEditingTask(task);
            setIsEditorOpen(true);
          }}
          onStatusChange={handleQuickStatus}
          onDelete={handleDeleteTask}
        />
      </div>

      {isEditorOpen ? (
        <TaskEditor
          task={editingTask}
          labels={labels}
          assignees={assignees}
          isBusy={isBusy}
          onClose={() => {
            setEditingTask(null);
            setIsEditorOpen(false);
          }}
          onCreateLabel={async (name) => {
            const color = labelColors[Math.floor(Math.random() * labelColors.length)];
            const data = await createTaskLabel({ name, color });
            setLabels(data.items);
          }}
          onDeleteLabel={async (labelId) => {
            const target = labels.find((item) => item.id === labelId);
            if (!target || !window.confirm(`删除标签「${target.name}」？已使用该标签的需求和任务会同步移除它。`)) {
              return;
            }
            await deleteTaskLabel(labelId);
            const data = await fetchTaskLabels();
            setLabels(data.items);
            await loadTasks();
          }}
          canEditAdminFields={isAdmin}
          onSave={handleSave}
        />
      ) : null}
    </section>
  );
}

function mergeTaskLabels(current: TaskLabel[], tasks: TaskItem[]) {
  const byId = new Map(current.map((item) => [item.id, item]));
  for (const task of tasks) {
    for (const label of task.labels) {
      byId.set(label.id, label);
    }
  }
  return Array.from(byId.values());
}

function mergeTaskAssignees(current: CurrentUser[], tasks: TaskItem[]) {
  const byId = new Map(current.map((item) => [item.id, item]));
  for (const task of tasks) {
    if (task.assignee) {
      byId.set(task.assignee.id, task.assignee);
    }
  }
  return Array.from(byId.values());
}


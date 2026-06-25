import { useEffect, useRef, useState } from "react";

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

const PAGE_SIZE = 20;

function readTaskListState() {
  const params = new URLSearchParams(window.location.search);
  const requestedPage = Number.parseInt(params.get("task_page") ?? "1", 10);
  const requestedStatus = params.get("task_status");
  return {
    page: Number.isFinite(requestedPage) && requestedPage > 0 ? requestedPage : 1,
    query: params.get("task_query") ?? "",
    status: (
      requestedStatus === "todo"
      || requestedStatus === "in_progress"
      || requestedStatus === "blocked"
      || requestedStatus === "done"
      || requestedStatus === "canceled"
        ? requestedStatus
        : "all"
    ) as TaskStatus | "all",
    assigneeId: params.get("task_assignee") ?? "",
    label: params.get("task_label") ?? "",
  };
}

export function TaskPage({ currentUser }: { currentUser: CurrentUser | null }) {
  const initialListState = useRef(readTaskListState()).current;
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [labels, setLabels] = useState<TaskLabel[]>([]);
  const [assignees, setAssignees] = useState<CurrentUser[]>([]);
  const [query, setQuery] = useState(initialListState.query);
  const [debouncedQuery, setDebouncedQuery] = useState(initialListState.query);
  const [status, setStatus] = useState<TaskStatus | "all">(initialListState.status);
  const [assigneeId, setAssigneeId] = useState(initialListState.assigneeId);
  const [label, setLabel] = useState(initialListState.label);
  const [page, setPage] = useState(initialListState.page);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [selectedTask, setSelectedTask] = useState<TaskItem | null>(null);
  const [editingTask, setEditingTask] = useState<TaskItem | null>(null);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const requestSequence = useRef(0);

  function writeTaskListState(
    next: {
      page: number;
      query: string;
      status: TaskStatus | "all";
      assigneeId: string;
      label: string;
    },
    mode: "push" | "replace" = "replace",
  ) {
    const params = new URLSearchParams(window.location.search);
    if (next.page > 1) params.set("task_page", String(next.page));
    else params.delete("task_page");
    if (next.query.trim()) params.set("task_query", next.query);
    else params.delete("task_query");
    if (next.status !== "all") params.set("task_status", next.status);
    else params.delete("task_status");
    if (next.assigneeId) params.set("task_assignee", next.assigneeId);
    else params.delete("task_assignee");
    if (next.label) params.set("task_label", next.label);
    else params.delete("task_label");
    const search = params.toString();
    window.history[mode === "push" ? "pushState" : "replaceState"](
      null,
      "",
      `${window.location.pathname}${search ? `?${search}` : ""}`,
    );
  }

  function updatePage(nextPage: number) {
    if (nextPage < 1 || (totalPages && nextPage > totalPages)) return;
    setPage(nextPage);
    setSelectedTask(null);
    const params = new URLSearchParams(window.location.search);
    params.delete("task");
    window.history.replaceState(null, "", `${window.location.pathname}${params.toString() ? `?${params.toString()}` : ""}`);
    writeTaskListState({ page: nextPage, query, status, assigneeId, label }, "push");
  }

  function updateQuery(nextQuery: string) {
    setQuery(nextQuery);
    setPage(1);
    setSelectedTask(null);
    writeTaskListState({ page: 1, query: nextQuery, status, assigneeId, label });
  }

  function updateStatus(nextStatus: TaskStatus | "all") {
    setStatus(nextStatus);
    setPage(1);
    setSelectedTask(null);
    writeTaskListState({ page: 1, query, status: nextStatus, assigneeId, label }, "push");
  }

  function updateAssignee(nextAssigneeId: string) {
    setAssigneeId(nextAssigneeId);
    setPage(1);
    setSelectedTask(null);
    writeTaskListState({ page: 1, query, status, assigneeId: nextAssigneeId, label }, "push");
  }

  function updateLabel(nextLabel: string) {
    setLabel(nextLabel);
    setPage(1);
    setSelectedTask(null);
    writeTaskListState({ page: 1, query, status, assigneeId, label: nextLabel }, "push");
  }

  async function loadTasks(requestedPage = page) {
    const requestId = ++requestSequence.current;
    const data = await fetchTasks({
      query: debouncedQuery,
      status,
      assigneeId,
      label,
      page: requestedPage,
      pageSize: PAGE_SIZE,
    });
    if (requestId !== requestSequence.current) return false;
    const lastAvailablePage = Math.max(1, data.total_pages);
    if (requestedPage > lastAvailablePage) {
      setPage(lastAvailablePage);
      writeTaskListState({ page: lastAvailablePage, query, status, assigneeId, label });
      return false;
    }
    setTasks(data.items);
    setTotal(data.total);
    setTotalPages(data.total_pages);
    setSelectedTask((current) => {
      const targetId = new URLSearchParams(window.location.search).get("task");
      if (targetId) {
        return data.items.find((item) => item.id === targetId) ?? null;
      }
      return current ? data.items.find((item) => item.id === current.id) ?? null : current;
    });
    return true;
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
    const timerId = window.setTimeout(() => setDebouncedQuery(query), 300);
    return () => window.clearTimeout(timerId);
  }, [query]);

  useEffect(() => {
    loadTasks().catch((error: Error) => setNotice(error.message));
  }, [assigneeId, debouncedQuery, label, page, status]);

  useEffect(() => {
    const handlePopState = () => {
      const next = readTaskListState();
      setPage(next.page);
      setQuery(next.query);
      setDebouncedQuery(next.query);
      setStatus(next.status);
      setAssigneeId(next.assigneeId);
      setLabel(next.label);
      setSelectedTask(null);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  async function handleSave(payload: TaskPayload) {
    setIsBusy(true);
    try {
      if (editingTask) {
        await updateTask(editingTask.id, payload);
        setNotice("任务已更新。");
      } else {
        await createTask(payload);
        setNotice("任务已创建。");
      }
      setIsEditorOpen(false);
      setEditingTask(null);
      await loadMeta();
      if (!editingTask && page !== 1) {
        updatePage(1);
      } else {
        await loadTasks(editingTask ? page : 1);
      }
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
      await loadTasks(page);
      setNotice("状态已更新。");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "状态更新失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleDeleteTask(task: TaskItem) {
    if (!window.confirm(`确定删除 TASK-${task.number} 吗？`)) {
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
      await loadTasks(page);
      setNotice("任务已删除。");
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
      <TaskToolbar onNewTask={() => setIsEditorOpen(true)} />

      <TaskFilters
        query={query}
        status={status}
        assigneeId={assigneeId}
        label={label}
        labels={labels}
        assignees={assignees}
        onQueryChange={updateQuery}
        onStatusChange={updateStatus}
        onAssigneeChange={updateAssignee}
        onLabelChange={updateLabel}
      />

      <div className="task-layout">
        <TaskList
          tasks={tasks}
          selectedTask={selectedTask}
          page={page}
          pageSize={PAGE_SIZE}
          total={total}
          totalPages={totalPages}
          onPageChange={updatePage}
          onSelect={setSelectedTask}
        />

        <TaskDetail
          task={selectedTask}
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
            if (!target || !window.confirm(`删除标签「${target.name}」？已使用该标签的需求草稿和任务会同步移除它。`)) {
              return;
            }
            await deleteTaskLabel(labelId);
            const data = await fetchTaskLabels();
            setLabels(data.items);
            await loadTasks();
          }}
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


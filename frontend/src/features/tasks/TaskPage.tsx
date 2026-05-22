import { FormEvent, useEffect, useMemo, useState } from "react";

import { API_BASE_URL, ApiError } from "../../api/client";
import { RichContentEditor, RichContentPreview } from "../rich-content/RichContentEditor";
import type { CurrentUser } from "../../types/requirement";
import type { FeishuTaskCandidate, FeishuTaskImportPreviewResponse, TaskItem, TaskLabel, TaskPayload, TaskStatus } from "../../types/task";
import {
  createFeishuImportedTasks,
  createTask,
  createTaskLabel,
  deleteTask,
  deleteTaskLabel,
  fetchTaskAssignees,
  fetchTaskLabels,
  fetchTasks,
  previewFeishuTaskImport,
  updateTask,
  uploadTaskImage,
} from "./api";

const statusLabels: Record<TaskStatus, string> = {
  todo: "待处理",
  in_progress: "进行中",
  blocked: "阻塞",
  done: "完成",
  canceled: "取消",
};

const statuses: Array<TaskStatus | "all"> = ["all", "todo", "in_progress", "blocked", "done", "canceled"];
const labelColors = ["#2f75d6", "#1f8a5b", "#b83245", "#8f5bd6", "#d68b2f"];

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
  const [isImportOpen, setIsImportOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  const isAdmin = currentUser?.role === "admin";

  async function loadTasks() {
    const data = await fetchTasks({ query, status, assigneeId, label });
    setTasks(data.items);
    setSelectedTask((current) => {
      const targetId = new URLSearchParams(window.location.search).get("task");
      if (targetId) {
        return data.items.find((item) => item.id === targetId) ?? null;
      }
      return current ? data.items.find((item) => item.id === current.id) ?? null : current;
    });
  }

  async function loadMeta() {
    const [labelData, assigneeData] = await Promise.all([fetchTaskLabels(), fetchTaskAssignees()]);
    setLabels(labelData.items);
    setAssignees(assigneeData.items);
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
      <div className="task-toolbar">
        <div>
          <p className="eyebrow">任务管理</p>
          <h2>开发任务</h2>
        </div>
        {isAdmin ? (
          <div className="task-toolbar-actions">
            <button className="secondary-button" type="button" onClick={() => setIsImportOpen(true)}>
              导入飞书对话
            </button>
            <button className="primary-button" type="button" onClick={() => setIsEditorOpen(true)}>
              新建任务
            </button>
          </div>
        ) : null}
      </div>

      <div className="task-filters">
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索任务" />
        <select value={status} onChange={(event) => setStatus(event.target.value as TaskStatus | "all")}>
          {statuses.map((item) => (
            <option key={item} value={item}>
              {item === "all" ? "全部状态" : statusLabels[item]} {item !== "all" && counts[item] ? `(${counts[item]})` : ""}
            </option>
          ))}
        </select>
        <select value={assigneeId} onChange={(event) => setAssigneeId(event.target.value)}>
          <option value="">全部负责人</option>
          {assignees.map((user) => (
            <option key={user.id} value={user.id}>{user.name}</option>
          ))}
        </select>
        <select value={label} onChange={(event) => setLabel(event.target.value)}>
          <option value="">全部标签</option>
          {labels.map((item) => (
            <option key={item.id} value={item.slug}>{item.name}</option>
          ))}
        </select>
      </div>

      <div className="task-layout">
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
                onClick={() => setSelectedTask(task)}
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
      {isImportOpen ? (
        <FeishuImportDialog
          isBusy={isBusy}
          onClose={() => setIsImportOpen(false)}
          onBusyChange={setIsBusy}
          onCreated={async (count) => {
            setIsImportOpen(false);
            setNotice(`已创建 ${count} 个任务。`);
            await loadTasks();
          }}
          onError={(message) => setNotice(message)}
        />
      ) : null}
    </section>
  );
}

function TaskDetail({
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
        <MarkdownPreview markdown={task.description_markdown || "暂无描述。"} />
      </section>
    </aside>
  );
}

function FeishuImportDialog({
  isBusy,
  onClose,
  onBusyChange,
  onCreated,
  onError,
}: {
  isBusy: boolean;
  onClose: () => void;
  onBusyChange: (busy: boolean) => void;
  onCreated: (count: number) => Promise<void>;
  onError: (message: string) => void;
}) {
  const [preview, setPreview] = useState<FeishuTaskImportPreviewResponse | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");

  async function handleFileChange(file: File | null) {
    if (!file) {
      return;
    }
    setError("");
    onBusyChange(true);
    try {
      const data = await previewFeishuTaskImport(file);
      setPreview(data);
      setSelectedIds(new Set(data.candidates.map((item) => item.candidate_id)));
    } catch (err) {
      const message = err instanceof Error ? err.message : "导入预览失败。";
      setError(message);
      onError(message);
    } finally {
      onBusyChange(false);
    }
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!preview) {
      return;
    }
    const candidates = preview.candidates.filter((item) => selectedIds.has(item.candidate_id));
    if (!candidates.length) {
      setError("请选择至少一个候选任务。");
      return;
    }
    setError("");
    onBusyChange(true);
    try {
      const data = await createFeishuImportedTasks(candidates);
      await onCreated(data.items.length);
    } catch (err) {
      const message = err instanceof Error ? err.message : "任务创建失败。";
      setError(message);
      onError(message);
    } finally {
      onBusyChange(false);
    }
  }

  function updateCandidate(candidateId: string, patch: Partial<FeishuTaskCandidate>) {
    setPreview((current) => {
      if (!current) {
        return current;
      }
      return {
        ...current,
        candidates: current.candidates.map((item) => (item.candidate_id === candidateId ? { ...item, ...patch } : item)),
      };
    });
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <form className="modal-panel feishu-import-panel" onSubmit={handleCreate}>
        <div className="modal-header">
          <div>
            <p className="eyebrow">飞书对话导入</p>
            <h2>生成候选任务</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="关闭">x</button>
        </div>
        <label className="file-import-control">
          <span>导出文件</span>
          <input
            type="file"
            accept=".zip,.jsonl,application/zip,application/jsonl,text/plain"
            disabled={isBusy}
            onChange={(event) => handleFileChange(event.target.files?.[0] ?? null)}
          />
        </label>
        <div className="import-help">
          <strong>可导入内容</strong>
          <p>支持飞书聊天导出的 zip，或解压后的 conversation-logs.jsonl。只会生成产品、研发、运营等可执行事项。</p>
          <p>不会导入简历、招聘、候选人评估、面试记录、闲聊和系统消息。</p>
        </div>
        {preview ? (
          <div className="import-summary">
            <span>{preview.conversations_count} 个会话</span>
            <span>{preview.messages_count} 条可用消息</span>
            <span>{preview.skipped_messages_count} 条已跳过</span>
          </div>
        ) : null}
        <div className="import-candidate-list">
          {preview?.candidates.map((candidate) => (
            <section className="import-candidate" key={candidate.candidate_id}>
              <label className="candidate-select-row">
                <input
                  type="checkbox"
                  checked={selectedIds.has(candidate.candidate_id)}
                  onChange={(event) => {
                    setSelectedIds((current) => {
                      const next = new Set(current);
                      if (event.target.checked) {
                        next.add(candidate.candidate_id);
                      } else {
                        next.delete(candidate.candidate_id);
                      }
                      return next;
                    });
                  }}
                />
                <span>创建此任务</span>
              </label>
              <label>
                <span>标题</span>
                <input
                  value={candidate.title}
                  minLength={3}
                  maxLength={160}
                  onChange={(event) => updateCandidate(candidate.candidate_id, { title: event.target.value })}
                />
              </label>
              <label>
                <span>描述</span>
                <textarea
                  value={candidate.description_markdown}
                  maxLength={20000}
                  onChange={(event) => updateCandidate(candidate.candidate_id, { description_markdown: event.target.value })}
                />
              </label>
              <div className="candidate-evidence">
                <span>来源证据</span>
                {candidate.evidence.map((item) => (
                  <blockquote key={`${candidate.candidate_id}-${item.message_id}`}>
                    <strong>{item.conversation_title || item.conversation_id}</strong>
                    {item.sender_name ? <small>{item.sender_name}</small> : null}
                    <p>{item.content}</p>
                  </blockquote>
                ))}
              </div>
              {candidate.duplicate_hints.length ? (
                <div className="duplicate-hints">
                  可能重复：{candidate.duplicate_hints.map((item) => `TASK-${item.number} ${item.title}`).join("、")}
                </div>
              ) : null}
            </section>
          ))}
          {preview && !preview.candidates.length ? (
            <div className="task-empty">
              未找到可创建的任务。请确认文件里包含明确的待办、修复、跟进、排查、回复等事项；简历和候选人评估会被过滤。
            </div>
          ) : null}
        </div>
        {error ? <div className="form-error">{error}</div> : null}
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={onClose}>取消</button>
          <button className="primary-button" type="submit" disabled={isBusy || !preview?.candidates.length}>
            {isBusy ? "处理中..." : "创建选中任务"}
          </button>
        </div>
      </form>
    </div>
  );
}

function TaskEditor({
  task,
  labels,
  assignees,
  isBusy,
  onClose,
  onCreateLabel,
  onDeleteLabel,
  canEditAdminFields,
  onSave,
}: {
  task: TaskItem | null;
  labels: TaskLabel[];
  assignees: CurrentUser[];
  isBusy: boolean;
  onClose: () => void;
  onCreateLabel: (name: string) => Promise<void>;
  onDeleteLabel: (labelId: string) => Promise<void>;
  canEditAdminFields: boolean;
  onSave: (payload: TaskPayload) => Promise<void>;
}) {
  const [title, setTitle] = useState(task?.title ?? "");
  const [description, setDescription] = useState(task?.description_markdown ?? "");
  const [status, setStatus] = useState<TaskStatus>(task?.status ?? "todo");
  const [assigneeId, setAssigneeId] = useState(task?.assignee?.id ?? "");
  const [selectedLabels, setSelectedLabels] = useState(task?.labels.map((item) => item.name) ?? []);
  const [newLabel, setNewLabel] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await onSave({
        title: title.trim(),
        description_markdown: description,
        status,
        assignee_user_id: assigneeId || null,
        labels: selectedLabels,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "保存失败。");
    }
  }

  async function handleImage(file: File) {
    const data = await uploadTaskImage(file);
    setDescription((current) => `${current}${current ? "\n\n" : ""}![${file.name}](${data.url})`);
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <form className="modal-panel task-editor" onSubmit={handleSubmit}>
        <div className="modal-header">
          <div>
            <p className="eyebrow">{task ? "编辑任务" : "新建任务"}</p>
            <h2>{task ? task.title : "开发任务"}</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="关闭">x</button>
        </div>
        <label>
          <span>标题</span>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            minLength={3}
            maxLength={160}
            required
            disabled={!canEditAdminFields}
          />
        </label>
        <div className="task-editor-grid">
          <label>
            <span>负责人</span>
            <select value={assigneeId} onChange={(event) => setAssigneeId(event.target.value)} disabled={!canEditAdminFields}>
              <option value="">未分配</option>
              {assignees.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
            </select>
          </label>
          <label>
            <span>状态</span>
            <select value={status} onChange={(event) => setStatus(event.target.value as TaskStatus)}>
              {statuses.filter((item): item is TaskStatus => item !== "all").map((item) => <option key={item} value={item}>{statusLabels[item]}</option>)}
            </select>
          </label>
        </div>
        <label>
          <span>标签</span>
          <div className="label-picker">
            {labels.map((item) => (
              <div
                key={item.id}
                className="label-choice"
                role="checkbox"
                aria-checked={selectedLabels.includes(item.name)}
                tabIndex={canEditAdminFields ? 0 : -1}
                onClick={() => {
                  if (!canEditAdminFields) return;
                  setSelectedLabels((current) =>
                    current.includes(item.name) ? current.filter((name) => name !== item.name) : [...current, item.name],
                  );
                }}
                onKeyDown={(event) => {
                  if (event.key !== " " && event.key !== "Enter") return;
                  event.preventDefault();
                  if (!canEditAdminFields) return;
                  setSelectedLabels((current) =>
                    current.includes(item.name) ? current.filter((name) => name !== item.name) : [...current, item.name],
                  );
                }}
              >
                <input
                  type="checkbox"
                  checked={selectedLabels.includes(item.name)}
                  disabled={!canEditAdminFields}
                  readOnly
                />
                <span className="label-dot" style={{ backgroundColor: item.color }} />
                <span>{item.name}</span>
                {canEditAdminFields ? (
                  <button
                    className="label-delete-button"
                    type="button"
                    aria-label={`删除标签 ${item.name}`}
                    onClick={(event) => {
                      event.stopPropagation();
                      onDeleteLabel(item.id).then(() => {
                        setSelectedLabels((current) => current.filter((name) => name !== item.name));
                      });
                    }}
                  >
                    ×
                  </button>
                ) : null}
              </div>
            ))}
          </div>
          {canEditAdminFields ? <div className="new-label-row">
            <input value={newLabel} onChange={(event) => setNewLabel(event.target.value)} placeholder="新标签" />
            <button className="secondary-button" type="button" onClick={() => {
              const name = newLabel.trim();
              if (!name) return;
              onCreateLabel(name).then(() => {
                setSelectedLabels((current) => [...new Set([...current, name])]);
                setNewLabel("");
              });
            }}>添加标签</button>
          </div> : null}
        </label>
        <MarkdownEditor value={description} onChange={setDescription} onImage={handleImage} />
        {error ? <div className="form-error">{error}</div> : null}
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={onClose}>取消</button>
          <button className="primary-button" type="submit" disabled={isBusy}>{isBusy ? "保存中..." : "保存任务"}</button>
        </div>
      </form>
    </div>
  );
}

function MarkdownEditor({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
  onImage: (file: File) => Promise<void>;
}) {
  return <RichContentEditor value={value} onChange={onChange} />;
}

function MarkdownPreview({ markdown }: { markdown: string }) {
  return <RichContentPreview markdown={markdown} />;
}

function renderMarkdown(markdown: string) {
  return markdown
    .split(/\n{2,}/)
    .map((block) => {
      const escaped = escapeHtml(block.trim());
      if (!escaped) return "";
      if (escaped.startsWith("- ")) {
        const items = escaped.split("\n").map((line) => `<li>${line.replace(/^- /, "")}</li>`).join("");
        return `<ul>${items}</ul>`;
      }
      const urlPattern = "((?:https?:\\/\\/|\\/)[^)]+)";
      const withImages = escaped.replace(
        new RegExp(`!\\[([^\\]]*)\\]\\(${urlPattern}\\)`, "g"),
        (_match: string, alt: string, url: string) => `<img src="${normalizeTaskImageUrl(url)}" alt="${alt}" />`,
      );
      const withLinks = withImages.replace(
        new RegExp(`\\[([^\\]]+)\\]\\(${urlPattern}\\)`, "g"),
        '<a href="$2" target="_blank" rel="noreferrer">$1</a>',
      );
      const withBold = withLinks.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      return `<p>${withBold.replace(/\n/g, "<br />")}</p>`;
    })
    .join("");
}

function normalizeTaskImageUrl(url: string) {
  const readableUrl = url.replace(/&amp;/g, "&");
  const objectName = readableUrl.match(/\/(?:featurevote\/)?(task-images\/[^?#]+)/)?.[1];
  if (!objectName) {
    return url;
  }
  return `${API_BASE_URL}/task-assets/images/${objectName}`;
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

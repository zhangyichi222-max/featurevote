import { FormEvent, useState } from "react";

import { ApiError } from "../../api/client";
import { LabelPicker } from "../../components/LabelPicker";
import { Modal } from "../../components/Modal";
import { RichContentEditor } from "../rich-content/RichContentEditor";
import type { CurrentUser } from "../../types/requirement";
import type { TaskItem, TaskLabel, TaskPayload, TaskStatus } from "../../types/task";
import { statuses, statusLabels } from "./constants";

export function TaskEditor({
  task,
  labels,
  assignees,
  isBusy,
  onClose,
  onCreateLabel,
  onDeleteLabel,
  onSave,
}: {
  task: TaskItem | null;
  labels: TaskLabel[];
  assignees: CurrentUser[];
  isBusy: boolean;
  onClose: () => void;
  onCreateLabel: (name: string) => Promise<void>;
  onDeleteLabel: (labelId: string) => Promise<void>;
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

  return (
    <Modal>
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
          />
        </label>
        <div className="task-editor-grid">
          <label>
            <span>负责人</span>
            <select value={assigneeId} onChange={(event) => setAssigneeId(event.target.value)}>
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
        <div className="task-editor-field">
          <span>标签</span>
          <LabelPicker
            labels={labels}
            selectedNames={selectedLabels}
            onToggle={(name) => {
              setSelectedLabels((current) =>
                current.includes(name) ? current.filter((selectedName) => selectedName !== name) : [...current, name],
              );
            }}
            onDelete={(item) => {
              if (!item.id) return;
              onDeleteLabel(item.id).then(() => {
                setSelectedLabels((current) => current.filter((name) => name !== item.name));
              });
            }}
          />
          <div className="new-label-row">
            <input value={newLabel} onChange={(event) => setNewLabel(event.target.value)} placeholder="新标签" />
            <button className="secondary-button" type="button" onClick={() => {
              const name = newLabel.trim();
              if (!name) return;
              onCreateLabel(name).then(() => {
                setSelectedLabels((current) => [...new Set([...current, name])]);
                setNewLabel("");
              });
            }}>添加标签</button>
          </div>
        </div>
        <RichContentEditor value={description} onChange={setDescription} />
        {error ? <div className="form-error">{error}</div> : null}
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={onClose}>取消</button>
          <button className="primary-button" type="submit" disabled={isBusy}>{isBusy ? "保存中..." : "保存任务"}</button>
        </div>
      </form>
    </Modal>
  );
}


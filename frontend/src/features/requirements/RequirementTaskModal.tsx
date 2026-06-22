import { FormEvent, useEffect, useState } from "react";

import { Modal } from "../../components/Modal";
import { RichContentEditor } from "../rich-content/RichContentEditor";
import type { CurrentUser, Requirement } from "../../types/requirement";
import { fetchTaskAssignees } from "../tasks/api";

export function RequirementTaskModal({
  item,
  isBusy,
  onClose,
  onSubmit,
}: {
  item: Requirement;
  isBusy: boolean;
  onClose: () => void;
  onSubmit: (payload: {
    title: string;
    description_markdown: string;
    assignee_user_id: string | null;
    labels: string[];
  }) => Promise<void>;
}) {
  const defaultDescription = [
    item.description,
    "",
    `来源需求：${item.req_id}`,
    `当前票数：${item.vote_count}`,
    `提交人：${item.creator_name}`,
    `链接：/?post=${item.id}`,
  ].join("\n");
  const [title, setTitle] = useState(item.title);
  const [description, setDescription] = useState(defaultDescription);
  const [assigneeId, setAssigneeId] = useState("");
  const [labels, setLabels] = useState("需求转入");
  const [assignees, setAssignees] = useState<CurrentUser[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchTaskAssignees()
      .then((data) => setAssignees(data.items))
      .catch((err: Error) => setError(err.message));
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await onSubmit({
        title: title.trim(),
        description_markdown: description,
        assignee_user_id: assigneeId || null,
        labels: labels
          .split(",")
          .map((label) => label.trim())
          .filter(Boolean),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建任务失败。");
    }
  }

  return (
    <Modal>
      <form className="modal-panel conversion-panel" onSubmit={handleSubmit}>
        <div className="modal-header">
          <div>
            <p className="eyebrow">转为任务</p>
            <h2>{item.req_id}</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="关闭">
            x
          </button>
        </div>
        <div className="conversion-source">
          <strong>{item.title}</strong>
          <span>{item.vote_count} 票 · {item.creator_name}</span>
        </div>
        <label>
          <span>任务标题</span>
          <input value={title} onChange={(event) => setTitle(event.target.value)} minLength={3} maxLength={160} required />
        </label>
        <label>
          <span>负责人</span>
          <select value={assigneeId} onChange={(event) => setAssigneeId(event.target.value)}>
            <option value="">暂不分配</option>
            {assignees.map((user) => (
              <option key={user.id} value={user.id}>{user.name}</option>
            ))}
          </select>
        </label>
        <label>
          <span>标签</span>
          <input value={labels} onChange={(event) => setLabels(event.target.value)} placeholder="需求转入, 前端" />
        </label>
        <div className="rich-field">
          <span>描述</span>
          <RichContentEditor value={description} onChange={setDescription} minRows={9} />
        </div>
        {error ? <div className="form-error">{error}</div> : null}
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={onClose}>取消</button>
          <button className="primary-button" type="submit" disabled={isBusy}>
            {isBusy ? "创建中..." : "创建任务并开始处理"}
          </button>
        </div>
      </form>
    </Modal>
  );
}



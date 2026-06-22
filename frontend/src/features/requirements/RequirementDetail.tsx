import { FormEvent, useState } from "react";

import { RichContentPreview } from "../rich-content/RichContentEditor";
import type { CommentItem, Requirement, RequirementStatus } from "../../types/requirement";
import { statusMeta, statusOrder } from "./constants";
import { formatDate } from "./utils";
import { StatusLozenge } from "./StatusLozenge";

export function RequirementDetail({
  item,
  comments,
  isBusy,
  onClose,
  onVote,
  onStatusChange,
  onArchive,
  onOpenTask,
  onComment,
  canWrite,
  isAdmin,
}: {
  item: Requirement;
  comments: CommentItem[];
  isBusy: boolean;
  onClose: () => void;
  onVote: (id: string) => Promise<void>;
  onStatusChange: (id: string, status: RequirementStatus) => Promise<void>;
  onArchive: (id: string) => Promise<void>;
  onOpenTask: (taskId: string) => void;
  onComment: (id: string, payload: { body: string }) => Promise<void>;
  canWrite: boolean;
  isAdmin: boolean;
}) {
  const [body, setBody] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    await onComment(item.id, { body });
    setBody("");
  }

  return (
    <div className="detail-backdrop" role="presentation">
      <section className="detail-panel" aria-label="建议详情">
        <header className="detail-header">
          <button className="back-button" type="button" onClick={onClose}>
            返回建议列表
          </button>
          <button className="icon-button" type="button" onClick={onClose} aria-label="关闭">
            x
          </button>
        </header>

        <div className="detail-layout">
          <article className="detail-main">
            <StatusLozenge status={item.status} />
            <h2>{item.title}</h2>
            {item.linked_task ? (
              <button className="linked-task-card" type="button" onClick={() => onOpenTask(item.linked_task!.id)}>
                <span>关联任务</span>
                <strong>TASK-{item.linked_task.number}</strong>
                <small>{item.linked_task.title}</small>
              </button>
            ) : null}
            <RichContentPreview markdown={item.description} className="detail-description" />
            {item.tags.length ? (
              <div className="suggestion-tags detail-tags" aria-label="标签">
                {item.tags.map((tag) => (
                  <small key={tag.slug} style={{ borderColor: tag.color }}>
                    <span className="label-dot" style={{ backgroundColor: tag.color }} />
                    {tag.name}
                  </small>
                ))}
              </div>
            ) : null}

            <section className="response-box">
              <h3>状态回复</h3>
              <p>{statusMeta[item.status].response}</p>
            </section>

            <section className="comments-section">
              <h3>讨论</h3>
              <div className="comment-list">
                {comments.map((comment) => (
                  <article key={comment.id} className="comment-item">
                    <strong>{comment.author_name}</strong>
                    <span>{formatDate(comment.created_at)}</span>
                    <p>{comment.body}</p>
                  </article>
                ))}
                {!comments.length ? <p className="comment-empty">还没有评论，来开始讨论吧。</p> : null}
              </div>
              {canWrite ? (
                <form className="comment-form" onSubmit={handleSubmit}>
                  <textarea
                    value={body}
                    onChange={(event) => setBody(event.target.value)}
                    placeholder="添加评论"
                    rows={4}
                    required
                  />
                  <button className="primary-button" type="submit" disabled={isBusy}>
                    {isBusy ? "发布中..." : "发布评论"}
                  </button>
                </form>
              ) : (
                <p className="comment-empty">通过飞书登录后参与讨论。</p>
              )}
            </section>
          </article>

          <aside className="detail-sidebar">
            <button className="big-vote-button" type="button" onClick={() => onVote(item.id)}>
              <span>^</span>
              <strong>{item.vote_count}</strong>
              <small>{item.has_voted ? "已投票" : "票"}</small>
            </button>
            {isAdmin ? (
              <div className="admin-controls">
                <label className="status-control">
                  <span>状态</span>
                  <select
                    value={item.status}
                    onChange={(event) => onStatusChange(item.id, event.target.value as RequirementStatus)}
                  >
                    {statusOrder.map((status) => (
                      <option key={status} value={status}>
                        {statusMeta[status].label}
                      </option>
                    ))}
                  </select>
                </label>
                <button className="danger-button" type="button" onClick={() => onArchive(item.id)} disabled={isBusy}>
                  删除建议
                </button>
              </div>
            ) : null}
          </aside>
        </div>
      </section>
    </div>
  );
}



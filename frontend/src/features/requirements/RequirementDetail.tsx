import { RichContentPreview } from "../rich-content/RichContentEditor";
import type { Requirement, RequirementStatus } from "../../types/requirement";
import { statusMeta, statusOrder } from "./constants";
import { StatusLozenge } from "./StatusLozenge";

export function RequirementDetail({
  item,
  isBusy,
  onClose,
  onVote,
  onStatusChange,
  onArchive,
  onOpenTask,
  onEdit,
  canEdit,
  canManage,
}: {
  item: Requirement;
  isBusy: boolean;
  onClose: () => void;
  onVote: (id: string) => Promise<void>;
  onStatusChange: (id: string, status: RequirementStatus) => Promise<void>;
  onArchive: (id: string) => Promise<void>;
  onOpenTask: (taskId: string) => void;
  onEdit: (item: Requirement) => void;
  canEdit: boolean;
  canManage: boolean;
}) {
  return (
    <div className="detail-backdrop" role="presentation">
      <section className="detail-panel" aria-label="需求草稿详情">
        <header className="detail-header">
          <button className="back-button" type="button" onClick={onClose}>
            返回需求草稿列表
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

          </article>

          <aside className="detail-sidebar">
            <button className="big-vote-button" type="button" onClick={() => onVote(item.id)}>
              <span>^</span>
              <strong>{item.vote_count}</strong>
              <small>{item.has_voted ? "已投票" : "票"}</small>
            </button>
            {canEdit ? (
              <button className="secondary-button" type="button" onClick={() => onEdit(item)} disabled={isBusy}>
                编辑需求草稿
              </button>
            ) : null}
            {canManage ? (
              <div className="management-controls">
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
                  删除需求草稿
                </button>
              </div>
            ) : null}
          </aside>
        </div>
      </section>
    </div>
  );
}


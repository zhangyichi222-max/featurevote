import { RichContentPreview } from "../rich-content/RichContentEditor";
import type { Requirement } from "../../types/requirement";

export function RequirementDetail({
  item,
  isBusy,
  onClose,
  onVote,
  onConvert,
  onArchive,
  onEdit,
  canEdit,
  canManage,
}: {
  item: Requirement;
  isBusy: boolean;
  onClose: () => void;
  onVote: (id: string) => Promise<void>;
  onConvert: (item: Requirement) => void;
  onArchive: (id: string) => Promise<void>;
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
            <h2>{item.title}</h2>
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
                <button className="primary-button" type="button" onClick={() => onConvert(item)} disabled={isBusy}>
                  采纳并创建任务
                </button>
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


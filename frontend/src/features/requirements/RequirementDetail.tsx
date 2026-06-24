import { RichContentPreview } from "../rich-content/RichContentEditor";
import type { Requirement } from "../../types/requirement";

export function RequirementDetail({
  item,
  isBusy,
  onVote,
  onConvert,
  onArchive,
  onEdit,
  canEdit,
  canManage,
}: {
  item: Requirement | null;
  isBusy: boolean;
  onVote: (id: string) => Promise<void>;
  onConvert: (item: Requirement) => void;
  onArchive: (id: string) => Promise<void>;
  onEdit: (item: Requirement) => void;
  canEdit: boolean;
  canManage: boolean;
}) {
  if (!item) {
    return (
      <aside className="requirement-detail requirement-detail-empty">
        <h3>草稿详情</h3>
        <p>选择一份需求草稿查看详情。</p>
      </aside>
    );
  }

  return (
    <aside className="requirement-detail" aria-label="需求草稿详情">
      <div className="requirement-detail-header">
        <div>
          <span className="requirement-detail-key">{item.req_id}</span>
          <h3>{item.title}</h3>
        </div>
        {canEdit ? (
          <button className="secondary-button" type="button" onClick={() => onEdit(item)} disabled={isBusy}>
            编辑
          </button>
        ) : null}
      </div>
      <div className="requirement-detail-actions">
        <button
          className={`requirement-detail-vote ${item.has_voted ? "voted" : ""}`}
          type="button"
          onClick={() => onVote(item.id)}
          disabled={isBusy}
        >
          <span>^</span>
          {item.has_voted ? "已投票" : "投票"} · {item.vote_count}
        </button>
        {canManage ? (
          <>
            <button className="primary-button" type="button" onClick={() => onConvert(item)} disabled={isBusy}>
              采纳并创建任务
            </button>
            <button className="danger-button" type="button" onClick={() => onArchive(item.id)} disabled={isBusy}>
              删除
            </button>
          </>
        ) : null}
      </div>
      <div className="requirement-properties">
        <div className="requirement-property-row">
          <span>提交人</span>
          <strong>{item.creator_name}</strong>
        </div>
        <div className="requirement-property-row requirement-property-labels">
          <span>标签</span>
          <div className="requirement-labels detail-labels">
            {item.tags.length ? item.tags.map((tag) => (
              <small key={tag.id} style={{ borderColor: tag.color }}>
                <span className="label-dot" style={{ backgroundColor: tag.color }} />
                {tag.name}
              </small>
            )) : <em>无</em>}
          </div>
        </div>
      </div>
      <section className="requirement-description-panel">
        <h4>描述</h4>
        <RichContentPreview markdown={item.description || "暂无描述。"} />
      </section>
    </aside>
  );
}


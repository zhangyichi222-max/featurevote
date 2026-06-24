import type { Requirement, RequirementTag } from "../../types/requirement";
import type { SortMode } from "./constants";

export function RequirementFilters({
  query,
  sortMode,
  label,
  labels,
  onQueryChange,
  onSortChange,
  onLabelChange,
}: {
  query: string;
  sortMode: SortMode;
  label: string;
  labels: RequirementTag[];
  onQueryChange: (value: string) => void;
  onSortChange: (value: SortMode) => void;
  onLabelChange: (value: string) => void;
}) {
  return (
    <div className="requirement-filters">
      <input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="搜索需求草稿" />
      <select value={sortMode} onChange={(event) => onSortChange(event.target.value as SortMode)}>
        <option value="popular">热度最高</option>
        <option value="recent">最近更新</option>
        <option value="newest">最新提交</option>
      </select>
      <select value={label} onChange={(event) => onLabelChange(event.target.value)}>
        <option value="">全部标签</option>
        {labels.map((item) => (
          <option key={item.id} value={item.slug}>{item.name}</option>
        ))}
      </select>
    </div>
  );
}

export function RequirementBoard({
  items,
  selectedItem,
  onSelect,
  onVote,
  canWrite,
}: {
  items: Requirement[];
  selectedItem: Requirement | null;
  onSelect: (item: Requirement) => void;
  onVote: (id: string) => Promise<void>;
  canWrite: boolean;
}) {
  return (
    <div className="requirement-main-pane">
      <div className="requirement-list-header">
        <span>票数</span>
        <span>需求草稿</span>
        <span>提交人</span>
        <span>标签</span>
      </div>
      <div className="requirement-list">
        {items.map((item) => (
          <RequirementListItem
            key={item.id}
            item={item}
            isSelected={selectedItem?.id === item.id}
            onSelect={onSelect}
            onVote={onVote}
            canWrite={canWrite}
          />
        ))}
        {!items.length ? (
          <div className="requirement-empty">
            <strong>暂无需求草稿</strong>
            <span>调整筛选条件，或新建一份需求草稿。</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function RequirementListItem({
  item,
  isSelected,
  onSelect,
  onVote,
  canWrite,
}: {
  item: Requirement;
  isSelected: boolean;
  onSelect: (item: Requirement) => void;
  onVote: (id: string) => Promise<void>;
  canWrite: boolean;
}) {
  return (
    <div className={`requirement-row ${isSelected ? "selected" : ""}`}>
      <button
        className={`requirement-vote ${item.has_voted ? "voted" : ""}`}
        type="button"
        onClick={() => onVote(item.id)}
        aria-label={canWrite ? "投票" : "登录后投票"}
        title={canWrite ? "投票" : "登录后投票"}
      >
        <span>^</span>
        <strong>{item.vote_count}</strong>
      </button>
      <button className="requirement-row-content" type="button" onClick={() => onSelect(item)}>
        <span className="requirement-title-cell">
          <span>
            <strong>{item.req_id}</strong>
            <b>{item.title}</b>
          </span>
        </span>
        <span className="requirement-creator-cell">{item.creator_name}</span>
        {item.tags.length ? (
          <span className="requirement-labels">
            {item.tags.map((tag) => (
              <small key={tag.id} style={{ borderColor: tag.color }}>
                <span className="label-dot" style={{ backgroundColor: tag.color }} />
                {tag.name}
              </small>
            ))}
          </span>
        ) : <span className="requirement-labels"><em>无</em></span>}
      </button>
    </div>
  );
}


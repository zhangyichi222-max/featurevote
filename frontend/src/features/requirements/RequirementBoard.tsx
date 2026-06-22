import { RichContentPreview } from "../rich-content/RichContentEditor";
import type { Requirement, RequirementStatus } from "../../types/requirement";
import type { SortMode, StatusFilter } from "./constants";
import { filterOptions } from "./constants";
import { formatDate } from "./utils";
import { StatusLozenge } from "./StatusLozenge";

export function RequirementBoard({
  items,
  query,
  statusFilter,
  sortMode,
  counts,
  onQueryChange,
  onStatusFilterChange,
  onSortChange,
  onSelect,
  onVote,
  canWrite,
}: {
  items: Requirement[];
  query: string;
  statusFilter: StatusFilter;
  sortMode: SortMode;
  counts: Record<RequirementStatus, number>;
  onQueryChange: (value: string) => void;
  onStatusFilterChange: (value: StatusFilter) => void;
  onSortChange: (value: SortMode) => void;
  onSelect: (id: string) => void;
  onVote: (id: string) => Promise<void>;
  canWrite: boolean;
}) {
  return (
    <div className="board-area">
      <div className="filter-row">
        <div className="status-tabs" aria-label="按状态筛选">
          {filterOptions.map((option) => (
            <button
              key={option.value}
              className={statusFilter === option.value ? "active" : ""}
              type="button"
              onClick={() => onStatusFilterChange(option.value)}
            >
              <span>{option.label}</span>
              {option.value !== "all" ? <small>{counts[option.value]}</small> : null}
            </button>
          ))}
        </div>
        <div className="search-sort-row">
          <label className="search-box">
            <span>搜索</span>
            <input
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder="搜索建议"
            />
          </label>
          <select value={sortMode} onChange={(event) => onSortChange(event.target.value as SortMode)}>
            <option value="popular">热度最高</option>
            <option value="recent">最近更新</option>
            <option value="newest">最新提交</option>
          </select>
        </div>
      </div>

      <div className="suggestion-list">
        {items.map((item) => (
          <RequirementListItem key={item.id} item={item} onSelect={onSelect} onVote={onVote} canWrite={canWrite} />
        ))}
        {!items.length ? (
          <div className="empty-state">
            <strong>没有找到建议。</strong>
            <span>换个筛选条件，或提交第一个想法。</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function RequirementListItem({
  item,
  onSelect,
  onVote,
  canWrite,
}: {
  item: Requirement;
  onSelect: (id: string) => void;
  onVote: (id: string) => Promise<void>;
  canWrite: boolean;
}) {
  return (
    <article className="suggestion-item">
      <button
        className="vote-box"
        type="button"
        onClick={() => onVote(item.id)}
        aria-label={canWrite ? "投票" : "登录后投票"}
        title={canWrite ? "投票" : "登录后投票"}
      >
        <span>^</span>
        <strong>{item.vote_count}</strong>
        <small>{item.has_voted ? "已投票" : "票"}</small>
      </button>
      <button className="suggestion-content" type="button" onClick={() => onSelect(item.id)}>
        <div className="suggestion-title-row">
          <h2>{item.title}</h2>
          <StatusLozenge status={item.status} />
        </div>
        <RichContentPreview markdown={item.description} className="suggestion-summary" />
        {item.tags.length ? (
          <span className="suggestion-tags">
            {item.tags.map((tag) => (
              <small key={tag.slug} style={{ borderColor: tag.color }}>
                <span className="label-dot" style={{ backgroundColor: tag.color }} />
                {tag.name}
              </small>
            ))}
          </span>
        ) : null}
        {item.linked_task ? (
          <span className="linked-task-chip">TASK-{item.linked_task.number}</span>
        ) : null}
      </button>
    </article>
  );
}



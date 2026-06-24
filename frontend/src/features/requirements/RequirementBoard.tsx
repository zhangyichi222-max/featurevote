import { RichContentPreview } from "../rich-content/RichContentEditor";
import type { Requirement } from "../../types/requirement";
import type { SortMode } from "./constants";

export function RequirementBoard({
  items,
  query,
  sortMode,
  onQueryChange,
  onSortChange,
  onSelect,
  onVote,
  canWrite,
}: {
  items: Requirement[];
  query: string;
  sortMode: SortMode;
  onQueryChange: (value: string) => void;
  onSortChange: (value: SortMode) => void;
  onSelect: (id: string) => void;
  onVote: (id: string) => Promise<void>;
  canWrite: boolean;
}) {
  return (
    <div className="board-area">
      <div className="filter-row">
        <div className="search-sort-row">
          <label className="search-box">
            <span>搜索</span>
            <input
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder="搜索需求草稿"
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
            <strong>没有找到需求草稿。</strong>
            <span>换个筛选条件，或提交第一份需求草稿。</span>
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
      </button>
    </article>
  );
}


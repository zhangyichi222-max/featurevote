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
  page,
  pageSize,
  total,
  totalPages,
  onPageChange,
  onSelect,
  onVote,
  canWrite,
}: {
  items: Requirement[];
  selectedItem: Requirement | null;
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  onPageChange: (page: number) => void;
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
      <RequirementPagination
        page={page}
        pageSize={pageSize}
        total={total}
        totalPages={totalPages}
        onPageChange={onPageChange}
      />
    </div>
  );
}

function RequirementPagination({
  page,
  pageSize,
  total,
  totalPages,
  onPageChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  if (!total) {
    return null;
  }
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  const pageItems = paginationItems(page, totalPages);
  return (
    <div className="requirement-pagination">
      <span>第 {start}–{end} 条，共 {total} 条</span>
      <div className="requirement-pagination-actions">
        <button type="button" onClick={() => onPageChange(page - 1)} disabled={page <= 1}>上一页</button>
        {pageItems.map((item) =>
          typeof item === "number" ? (
            <button
              key={item}
              className={item === page ? "active" : ""}
              type="button"
              onClick={() => onPageChange(item)}
              aria-current={item === page ? "page" : undefined}
            >
              {item}
            </button>
          ) : <span key={item}>…</span>,
        )}
        <button type="button" onClick={() => onPageChange(page + 1)} disabled={page >= totalPages}>下一页</button>
      </div>
    </div>
  );
}

function paginationItems(page: number, totalPages: number): Array<number | string> {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }
  const items: Array<number | string> = [1];
  if (page > 4) {
    items.push("left-ellipsis");
  }
  const start = Math.max(2, page - 1);
  const end = Math.min(totalPages - 1, page + 1);
  for (let current = start; current <= end; current += 1) {
    items.push(current);
  }
  if (page < totalPages - 3) {
    items.push("right-ellipsis");
  }
  items.push(totalPages);
  return items;
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


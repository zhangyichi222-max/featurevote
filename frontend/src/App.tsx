import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  createComment,
  createRequirement,
  fetchComments,
  fetchRequirements,
  updateRequirementStatus,
  voteRequirement,
} from "./features/requirements/api";
import type { CommentItem, Requirement, RequirementStatus } from "./types/requirement";

type SortMode = "popular" | "newest" | "recent";
type StatusFilter = "all" | RequirementStatus;

const statusMeta: Record<
  RequirementStatus,
  {
    label: string;
    tone: string;
    response: string;
  }
> = {
  backlog: {
    label: "Open",
    tone: "neutral",
    response: "This suggestion is open for votes and discussion.",
  },
  approved: {
    label: "Planned",
    tone: "info",
    response: "This suggestion has enough signal to move into planning.",
  },
  in_progress: {
    label: "In Progress",
    tone: "warning",
    response: "The team is actively working on this suggestion.",
  },
  done: {
    label: "Completed",
    tone: "success",
    response: "This suggestion has shipped or has been resolved.",
  },
  rejected: {
    label: "Declined",
    tone: "danger",
    response: "This suggestion is not planned for the current product direction.",
  },
};

const statusOrder: RequirementStatus[] = ["backlog", "approved", "in_progress", "done", "rejected"];

const filterOptions: Array<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "backlog", label: "Open" },
  { value: "approved", label: "Planned" },
  { value: "in_progress", label: "In progress" },
  { value: "done", label: "Completed" },
  { value: "rejected", label: "Declined" },
];

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(value));
}

function normalize(value: string) {
  return value.trim().toLowerCase();
}

export default function App() {
  const [items, setItems] = useState<Requirement[]>([]);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const [sortMode, setSortMode] = useState<SortMode>("popular");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [comments, setComments] = useState<Record<string, CommentItem[]>>({});
  const [notice, setNotice] = useState("Loading suggestions...");
  const [isComposerOpen, setIsComposerOpen] = useState(false);
  const [isBusy, setIsBusy] = useState(false);

  const selectedItem = useMemo(
    () => items.find((item) => item.id === selectedId) ?? null,
    [items, selectedId],
  );

  const visibleItems = useMemo(() => {
    const keyword = normalize(query);
    return items
      .filter((item) => statusFilter === "all" || item.status === statusFilter)
      .filter((item) => {
        if (!keyword) {
          return true;
        }
        return normalize(`${item.title} ${item.description} ${item.req_id}`).includes(keyword);
      })
      .sort((left, right) => {
        if (sortMode === "popular") {
          return right.vote_count - left.vote_count || right.updated_at.localeCompare(left.updated_at);
        }
        if (sortMode === "recent") {
          return right.updated_at.localeCompare(left.updated_at);
        }
        return right.created_at.localeCompare(left.created_at);
      });
  }, [items, query, sortMode, statusFilter]);

  const counts = useMemo(() => {
    return statusOrder.reduce<Record<RequirementStatus, number>>((result, status) => {
      result[status] = items.filter((item) => item.status === status).length;
      return result;
    }, {} as Record<RequirementStatus, number>);
  }, [items]);

  async function loadRequirements() {
    const data = await fetchRequirements();
    setItems(data.items);
    setNotice(data.items.length ? "Suggestions synced." : "No suggestions yet. Start the board.");
  }

  useEffect(() => {
    loadRequirements().catch((error: Error) => setNotice(error.message));
  }, []);

  useEffect(() => {
    if (!selectedId || comments[selectedId]) {
      return;
    }

    fetchComments(selectedId)
      .then((data) => setComments((current) => ({ ...current, [selectedId]: data.items })))
      .catch(() => setComments((current) => ({ ...current, [selectedId]: [] })));
  }, [comments, selectedId]);

  async function handleCreate(payload: {
    title: string;
    description: string;
    creator_name: string;
    creator_open_id: string;
  }) {
    setIsBusy(true);
    try {
      await createRequirement(payload);
      setNotice("Suggestion submitted.");
      setIsComposerOpen(false);
      await loadRequirements();
    } finally {
      setIsBusy(false);
    }
  }

  async function handleVote(requirementId: string) {
    setIsBusy(true);
    try {
      await voteRequirement(requirementId, {
        voter_name: "Anonymous voter",
        voter_open_id: "local-demo-user",
      });
      setNotice("Vote recorded.");
      await loadRequirements();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Vote failed.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleStatusChange(requirementId: string, status: RequirementStatus) {
    setIsBusy(true);
    try {
      await updateRequirementStatus(requirementId, { status });
      setNotice(`Status changed to ${statusMeta[status].label}.`);
      await loadRequirements();
    } finally {
      setIsBusy(false);
    }
  }

  async function handleComment(requirementId: string, payload: { author_name: string; body: string }) {
    setIsBusy(true);
    try {
      await createComment(requirementId, payload);
      const data = await fetchComments(requirementId);
      setComments((current) => ({ ...current, [requirementId]: data.items }));
      setNotice("Comment added.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <main className="app-shell">
      <Header />

      <section className="home-layout">
        <aside className="welcome-column">
          <p className="eyebrow">FeatureVote</p>
          <h1>Share feedback. Vote on what matters.</h1>
          <p className="welcome-copy">
            A focused feedback board for collecting suggestions, measuring demand, and showing
            progress back to the people who asked.
          </p>
          <div className="board-stats" aria-label="Suggestion summary">
            <SummaryStat label="Suggestions" value={items.length} />
            <SummaryStat label="Votes" value={items.reduce((total, item) => total + item.vote_count, 0)} />
            <SummaryStat label="Planned" value={counts.approved + counts.in_progress} />
          </div>
        </aside>

        <section className="suggestions-column">
          <button className="new-suggestion-button" type="button" onClick={() => setIsComposerOpen(true)}>
            <span className="plus-icon">+</span>
            <span>What should we build next?</span>
          </button>

          <SuggestionBoard
            items={visibleItems}
            query={query}
            statusFilter={statusFilter}
            sortMode={sortMode}
            counts={counts}
            notice={notice}
            onQueryChange={setQuery}
            onStatusFilterChange={setStatusFilter}
            onSortChange={setSortMode}
            onSelect={setSelectedId}
            onVote={handleVote}
          />
        </section>
      </section>

      {isComposerOpen ? (
        <SuggestionComposer
          isBusy={isBusy}
          onClose={() => setIsComposerOpen(false)}
          onSubmit={handleCreate}
        />
      ) : null}

      {selectedItem ? (
        <SuggestionDetail
          item={selectedItem}
          comments={comments[selectedItem.id] ?? []}
          isBusy={isBusy}
          onClose={() => setSelectedId(null)}
          onVote={handleVote}
          onStatusChange={handleStatusChange}
          onComment={handleComment}
        />
      ) : null}
    </main>
  );
}

function Header() {
  return (
    <header className="topbar">
      <div className="brand-mark" aria-label="FeatureVote">
        <span>F</span>
        <strong>FeatureVote</strong>
      </div>
    </header>
  );
}

function SummaryStat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function SuggestionBoard({
  items,
  query,
  statusFilter,
  sortMode,
  counts,
  notice,
  onQueryChange,
  onStatusFilterChange,
  onSortChange,
  onSelect,
  onVote,
}: {
  items: Requirement[];
  query: string;
  statusFilter: StatusFilter;
  sortMode: SortMode;
  counts: Record<RequirementStatus, number>;
  notice: string;
  onQueryChange: (value: string) => void;
  onStatusFilterChange: (value: StatusFilter) => void;
  onSortChange: (value: SortMode) => void;
  onSelect: (id: string) => void;
  onVote: (id: string) => Promise<void>;
}) {
  return (
    <div className="board-area">
      <div className="filter-row">
        <div className="status-tabs" aria-label="Filter by status">
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
            <span>Search</span>
            <input
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder="Search suggestions"
            />
          </label>
          <select value={sortMode} onChange={(event) => onSortChange(event.target.value as SortMode)}>
            <option value="popular">Trending</option>
            <option value="recent">Recently updated</option>
            <option value="newest">Newest</option>
          </select>
        </div>
      </div>

      <div className="sync-notice">{notice}</div>

      <div className="suggestion-list">
        {items.map((item) => (
          <SuggestionListItem key={item.id} item={item} onSelect={onSelect} onVote={onVote} />
        ))}
        {!items.length ? (
          <div className="empty-state">
            <strong>No suggestions found.</strong>
            <span>Try another filter or share the first idea.</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function SuggestionListItem({
  item,
  onSelect,
  onVote,
}: {
  item: Requirement;
  onSelect: (id: string) => void;
  onVote: (id: string) => Promise<void>;
}) {
  return (
    <article className="suggestion-item">
      <button className="vote-box" type="button" onClick={() => onVote(item.id)} aria-label="Vote">
        <span>^</span>
        <strong>{item.vote_count}</strong>
        <small>{item.vote_count === 1 ? "vote" : "votes"}</small>
      </button>
      <button className="suggestion-content" type="button" onClick={() => onSelect(item.id)}>
        <div className="suggestion-title-row">
          <h2>{item.title}</h2>
          <StatusLozenge status={item.status} />
        </div>
        <p>{item.description}</p>
        <div className="suggestion-meta">
          <span>{item.req_id}</span>
          <span>{item.creator_name || "Anonymous"}</span>
          <span>Updated {formatDate(item.updated_at)}</span>
        </div>
      </button>
    </article>
  );
}

function SuggestionComposer({
  isBusy,
  onClose,
  onSubmit,
}: {
  isBusy: boolean;
  onClose: () => void;
  onSubmit: (payload: {
    title: string;
    description: string;
    creator_name: string;
    creator_open_id: string;
  }) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [name, setName] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    onSubmit({
      title,
      description,
      creator_name: name || "Anonymous",
      creator_open_id: name ? `local-${normalize(name).replace(/\s+/g, "-")}` : "anonymous",
    });
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <form className="modal-panel composer-panel" onSubmit={handleSubmit}>
        <div className="modal-header">
          <div>
            <p className="eyebrow">New suggestion</p>
            <h2>Share feedback</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close">
            x
          </button>
        </div>
        <label>
          <span>Title</span>
          <input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={120} required />
        </label>
        <label>
          <span>Description</span>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={7}
            required
          />
        </label>
        <label>
          <span>Name</span>
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Optional" />
        </label>
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="primary-button" type="submit" disabled={isBusy}>
            {isBusy ? "Submitting..." : "Submit suggestion"}
          </button>
        </div>
      </form>
    </div>
  );
}

function SuggestionDetail({
  item,
  comments,
  isBusy,
  onClose,
  onVote,
  onStatusChange,
  onComment,
}: {
  item: Requirement;
  comments: CommentItem[];
  isBusy: boolean;
  onClose: () => void;
  onVote: (id: string) => Promise<void>;
  onStatusChange: (id: string, status: RequirementStatus) => Promise<void>;
  onComment: (id: string, payload: { author_name: string; body: string }) => Promise<void>;
}) {
  const [authorName, setAuthorName] = useState("");
  const [body, setBody] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    await onComment(item.id, { author_name: authorName || "Anonymous", body });
    setAuthorName("");
    setBody("");
  }

  return (
    <div className="detail-backdrop" role="presentation">
      <section className="detail-panel" aria-label="Suggestion details">
        <header className="detail-header">
          <button className="back-button" type="button" onClick={onClose}>
            &lt;- Back to suggestions
          </button>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close">
            x
          </button>
        </header>

        <div className="detail-layout">
          <article className="detail-main">
            <StatusLozenge status={item.status} />
            <h2>{item.title}</h2>
            <p className="detail-description">{item.description}</p>

            <section className="response-box">
              <h3>Status response</h3>
              <p>{statusMeta[item.status].response}</p>
            </section>

            <section className="comments-section">
              <h3>Discussion</h3>
              <div className="comment-list">
                {comments.map((comment) => (
                  <article key={comment.id} className="comment-item">
                    <strong>{comment.author_name}</strong>
                    <span>{formatDate(comment.created_at)}</span>
                    <p>{comment.body}</p>
                  </article>
                ))}
                {!comments.length ? <p className="comment-empty">No comments yet. Start the discussion.</p> : null}
              </div>
              <form className="comment-form" onSubmit={handleSubmit}>
                <input value={authorName} onChange={(event) => setAuthorName(event.target.value)} placeholder="Name" />
                <textarea
                  value={body}
                  onChange={(event) => setBody(event.target.value)}
                  placeholder="Add a comment"
                  rows={4}
                  required
                />
                <button className="primary-button" type="submit" disabled={isBusy}>
                  {isBusy ? "Posting..." : "Post comment"}
                </button>
              </form>
            </section>
          </article>

          <aside className="detail-sidebar">
            <button className="big-vote-button" type="button" onClick={() => onVote(item.id)}>
              <span>^</span>
              <strong>{item.vote_count}</strong>
              <small>{item.vote_count === 1 ? "vote" : "votes"}</small>
            </button>
            <label className="status-control">
              <span>Status</span>
              <select value={item.status} onChange={(event) => onStatusChange(item.id, event.target.value as RequirementStatus)}>
                {statusOrder.map((status) => (
                  <option key={status} value={status}>
                    {statusMeta[status].label}
                  </option>
                ))}
              </select>
            </label>
            <dl className="detail-meta">
              <div>
                <dt>Submitted by</dt>
                <dd>{item.creator_name || "Anonymous"}</dd>
              </div>
              <div>
                <dt>Reference</dt>
                <dd>{item.req_id}</dd>
              </div>
              <div>
                <dt>Updated</dt>
                <dd>{formatDate(item.updated_at)}</dd>
              </div>
            </dl>
          </aside>
        </div>
      </section>
    </div>
  );
}

function StatusLozenge({ status }: { status: RequirementStatus }) {
  const meta = statusMeta[status];
  return <span className={`status-lozenge status-${meta.tone}`}>{meta.label}</span>;
}

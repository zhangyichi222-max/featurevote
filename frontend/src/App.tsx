import { FormEvent, useEffect, useMemo, useState } from "react";

import { ApiError, startFeishuBrowserLogin } from "./api/client";
import {
  archiveRequirement,
  createComment,
  createRequirement,
  draftRequirementWithAi,
  exchangeFeishuClientCode,
  fetchComments,
  fetchCurrentUser,
  fetchRequirements,
  findSimilarRequirements,
  logoutCurrentUser,
  updateRequirementStatus,
  voteRequirement,
} from "./features/requirements/api";
import type { CommentItem, CurrentUser, Requirement, RequirementStatus, SimilarRequirement } from "./types/requirement";

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

type ComposerField = "title" | "description";

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
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(true);

  const isAdmin = currentUser?.role === "admin";

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

  async function loadCurrentUser() {
    try {
      setCurrentUser(await fetchCurrentUser());
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setCurrentUser(null);
        return;
      }
      setNotice(error instanceof Error ? error.message : "Could not load current user.");
    } finally {
      setIsAuthLoading(false);
    }
  }

  useEffect(() => {
    loadRequirements().catch((error: Error) => setNotice(error.message));
    loadCurrentUser();
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("feishu_client_code");
    if (!code) {
      return;
    }

    exchangeFeishuClientCode(code)
      .then(() => loadCurrentUser())
      .then(() => {
        params.delete("feishu_client_code");
        const nextSearch = params.toString();
        window.history.replaceState(null, "", `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ""}`);
        setNotice("Signed in with Feishu.");
      })
      .catch((error: Error) => setNotice(error.message));
  }, []);

  useEffect(() => {
    if (!selectedId || comments[selectedId]) {
      return;
    }

    fetchComments(selectedId)
      .then((data) => setComments((current) => ({ ...current, [selectedId]: data.items })))
      .catch(() => setComments((current) => ({ ...current, [selectedId]: [] })));
  }, [comments, selectedId]);

  function requireLogin(action: string) {
    if (currentUser) {
      return true;
    }
    setNotice(`Sign in with Feishu to ${action}.`);
    return false;
  }

  async function handleLogout() {
    setIsBusy(true);
    try {
      await logoutCurrentUser();
      setCurrentUser(null);
      setNotice("Signed out. Browsing is still available.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Sign out failed.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCreate(payload: { title: string; description: string }) {
    if (!requireLogin("submit suggestions")) {
      throw new Error("Sign in required.");
    }
    setIsBusy(true);
    try {
      await createRequirement(payload);
      setNotice("Suggestion submitted.");
      setIsComposerOpen(false);
      await loadRequirements();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Suggestion submission failed.");
      throw error;
    } finally {
      setIsBusy(false);
    }
  }

  async function handleVote(requirementId: string) {
    if (!requireLogin("vote")) {
      return;
    }
    setIsBusy(true);
    try {
      await voteRequirement(requirementId);
      setNotice("Vote recorded.");
      await loadRequirements();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Vote failed.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleStatusChange(requirementId: string, status: RequirementStatus) {
    if (!isAdmin) {
      setNotice("Only admins can change status.");
      return;
    }
    setIsBusy(true);
    try {
      await updateRequirementStatus(requirementId, { status });
      setNotice(`Status changed to ${statusMeta[status].label}.`);
      await loadRequirements();
    } finally {
      setIsBusy(false);
    }
  }

  async function handleArchive(requirementId: string) {
    if (!isAdmin) {
      setNotice("Only admins can archive suggestions.");
      return;
    }
    setIsBusy(true);
    try {
      await archiveRequirement(requirementId);
      setSelectedId(null);
      setNotice("Suggestion archived.");
      await loadRequirements();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Archive failed.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleComment(requirementId: string, payload: { body: string }) {
    if (!requireLogin("comment")) {
      return;
    }
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
      <Header
        currentUser={currentUser}
        isAuthLoading={isAuthLoading}
        isBusy={isBusy}
        onLogin={startFeishuBrowserLogin}
        onLogout={handleLogout}
      />

      <section className="home-layout">
        <aside className="welcome-column">
          <p className="eyebrow">FeatureVote</p>
          <h1>Share feedback. Vote on what matters.</h1>
          <p className="welcome-copy">A focused place to share feedback and vote on what matters.</p>
        </aside>

        <section className="suggestions-column">
          <button
            className="new-suggestion-button"
            type="button"
            onClick={() => {
              if (requireLogin("submit suggestions")) {
                setIsComposerOpen(true);
              }
            }}
          >
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
            canWrite={Boolean(currentUser)}
          />
        </section>
      </section>

      {isComposerOpen ? (
        <SuggestionComposer
          isBusy={isBusy}
          onClose={() => setIsComposerOpen(false)}
          onOpenExisting={(id) => {
            setIsComposerOpen(false);
            setSelectedId(id);
          }}
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
          onArchive={handleArchive}
          onComment={handleComment}
          canWrite={Boolean(currentUser)}
          isAdmin={isAdmin}
        />
      ) : null}
    </main>
  );
}

function Header({
  currentUser,
  isAuthLoading,
  isBusy,
  onLogin,
  onLogout,
}: {
  currentUser: CurrentUser | null;
  isAuthLoading: boolean;
  isBusy: boolean;
  onLogin: () => void;
  onLogout: () => Promise<void>;
}) {
  return (
    <header className="topbar">
      <div className="brand-mark" aria-label="FeatureVote">
        <span>F</span>
        <strong>FeatureVote</strong>
      </div>
      <div className="auth-controls">
        {currentUser ? (
          <>
            <div className="user-pill">
              <strong>{currentUser.name}</strong>
              <span>{currentUser.role === "admin" ? "Admin" : "Member"}</span>
            </div>
            <button className="secondary-button" type="button" onClick={onLogout} disabled={isBusy}>
              Sign out
            </button>
          </>
        ) : (
          <button className="primary-button" type="button" onClick={onLogin} disabled={isAuthLoading}>
            {isAuthLoading ? "Checking..." : "Sign in with Feishu"}
          </button>
        )}
      </div>
    </header>
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
  canWrite,
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
  canWrite: boolean;
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
          <SuggestionListItem key={item.id} item={item} onSelect={onSelect} onVote={onVote} canWrite={canWrite} />
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
        aria-label={canWrite ? "Vote" : "Sign in to vote"}
        title={canWrite ? "Vote" : "Sign in to vote"}
      >
        <span>^</span>
        <strong>{item.vote_count}</strong>
        <small>{item.has_voted ? "voted" : item.vote_count === 1 ? "vote" : "votes"}</small>
      </button>
      <button className="suggestion-content" type="button" onClick={() => onSelect(item.id)}>
        <div className="suggestion-title-row">
          <h2>{item.title}</h2>
          <StatusLozenge status={item.status} />
        </div>
        <p>{item.description}</p>
      </button>
    </article>
  );
}

function SuggestionComposer({
  isBusy,
  onClose,
  onOpenExisting,
  onSubmit,
}: {
  isBusy: boolean;
  onClose: () => void;
  onOpenExisting: (id: string) => void;
  onSubmit: (payload: { title: string; description: string }) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [roughIdea, setRoughIdea] = useState("");
  const [similarItems, setSimilarItems] = useState<SimilarRequirement[]>([]);
  const [isCheckingSimilar, setIsCheckingSimilar] = useState(false);
  const [similarAiEnhanced, setSimilarAiEnhanced] = useState(false);
  const [submitConfirmed, setSubmitConfirmed] = useState(false);
  const [isDrafting, setIsDrafting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [draftNotice, setDraftNotice] = useState("");
  const [isDraftError, setIsDraftError] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<ComposerField, string>>>({});
  const hasHighSimilarity = similarItems.some((item) => item.is_high_confidence);

  useEffect(() => {
    const queryText = `${title} ${description}`.trim();
    setSubmitConfirmed(false);
    if (queryText.length < 5) {
      setSimilarItems([]);
      setSimilarAiEnhanced(false);
      setIsCheckingSimilar(false);
      return;
    }

    let isCurrent = true;
    setIsCheckingSimilar(true);
    const timeoutId = window.setTimeout(() => {
      findSimilarRequirements({ title, description, limit: 3 })
        .then((data) => {
          if (!isCurrent) {
            return;
          }
          setSimilarItems(data.items);
          setSimilarAiEnhanced(data.ai_enhanced);
        })
        .catch(() => {
          if (isCurrent) {
            setSimilarItems([]);
            setSimilarAiEnhanced(false);
          }
        })
        .finally(() => {
          if (isCurrent) {
            setIsCheckingSimilar(false);
          }
        });
    }, 400);

    return () => {
      isCurrent = false;
      window.clearTimeout(timeoutId);
    };
  }, [description, title]);

  async function handleDraft() {
    const trimmedIdea = roughIdea.trim();
    if (trimmedIdea.length < 20) {
      setDraftNotice("请至少输入 20 个字，让 AI 有足够上下文生成需求。");
      setIsDraftError(true);
      return;
    }

    setIsDrafting(true);
    setDraftNotice("");
    setIsDraftError(false);
    try {
      const draft = await draftRequirementWithAi({ idea: trimmedIdea });
      setTitle(draft.title);
      setDescription(draft.description);
      setSubmitConfirmed(false);
      setFieldErrors({});
      setSubmitError("");
      setDraftNotice("AI 已生成草稿，你可以继续编辑后提交。");
    } catch (error) {
      setDraftNotice(error instanceof Error ? error.message : "AI 生成失败，请稍后重试。");
      setIsDraftError(true);
    } finally {
      setIsDrafting(false);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const nextFieldErrors: Partial<Record<ComposerField, string>> = {};
    const trimmedTitle = title.trim();
    const trimmedDescription = description.trim();

    if (trimmedTitle.length < 3) {
      nextFieldErrors.title = "Title must be at least 3 characters.";
    }
    if (!trimmedDescription) {
      nextFieldErrors.description = "Description is required.";
    }

    setFieldErrors(nextFieldErrors);
    if (Object.keys(nextFieldErrors).length > 0) {
      setSubmitError("Please fix the highlighted fields before submitting.");
      return;
    }

    if (hasHighSimilarity && !submitConfirmed) {
      setSubmitConfirmed(true);
      setSubmitError("Similar suggestions found. Review them, or click Submit anyway to continue.");
      return;
    }

    setSubmitError("");

    try {
      await onSubmit({
        title: trimmedTitle,
        description: trimmedDescription,
      });
    } catch (error) {
      if (error instanceof ApiError) {
        setSubmitError(error.message);
        setFieldErrors({
          title: error.fieldErrors.title,
          description: error.fieldErrors.description,
        });
        return;
      }

      setSubmitError(error instanceof Error ? error.message : "Suggestion submission failed.");
    }
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
        <section className="ai-draft-box" aria-label="AI suggestion draft">
          <label>
            <span>一句话想法</span>
            <textarea
              value={roughIdea}
              onChange={(event) => {
                setRoughIdea(event.target.value);
                setDraftNotice("");
                setIsDraftError(false);
              }}
              rows={3}
              maxLength={12000}
              placeholder="例如：希望可以按部门筛选投票结果，方便判断不同团队最关心什么"
            />
          </label>
          <div className="ai-draft-actions">
            <button className="secondary-button" type="button" onClick={handleDraft} disabled={isDrafting || isBusy}>
              {isDrafting ? "AI 生成中..." : "AI 生成需求"}
            </button>
            <small className={isDraftError ? "field-error" : "field-hint"}>
              {draftNotice || "AI 会生成标题和“问题 / 场景 / 期望结果”，提交前仍可编辑。"}
            </small>
          </div>
        </section>
        <label>
          <span>Title</span>
          <input
            value={title}
            onChange={(event) => {
              setTitle(event.target.value);
              setSubmitConfirmed(false);
              setFieldErrors((current) => ({ ...current, title: undefined }));
              setSubmitError("");
            }}
            maxLength={120}
            minLength={3}
            required
            aria-invalid={Boolean(fieldErrors.title)}
            className={fieldErrors.title ? "input-error" : ""}
          />
          <small className={fieldErrors.title ? "field-error" : "field-hint"}>
            {fieldErrors.title ?? "Use at least 3 characters so others can understand the idea quickly."}
          </small>
        </label>
        <label>
          <span>Description</span>
          <textarea
            value={description}
            onChange={(event) => {
              setDescription(event.target.value);
              setSubmitConfirmed(false);
              setFieldErrors((current) => ({ ...current, description: undefined }));
              setSubmitError("");
            }}
            rows={7}
            required
            aria-invalid={Boolean(fieldErrors.description)}
            className={fieldErrors.description ? "input-error" : ""}
          />
          <small className={fieldErrors.description ? "field-error" : "field-hint"}>
            {fieldErrors.description ?? "Add enough detail for the team to understand the request."}
          </small>
        </label>
        <SimilarRequirementPrompt
          items={similarItems}
          isChecking={isCheckingSimilar}
          aiEnhanced={similarAiEnhanced}
          onOpenExisting={onOpenExisting}
        />
        {submitError ? <div className="form-error">{submitError}</div> : null}
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="primary-button" type="submit" disabled={isBusy}>
            {isBusy ? "Submitting..." : hasHighSimilarity && !submitConfirmed ? "Review similar suggestions" : submitConfirmed ? "Submit anyway" : "Submit suggestion"}
          </button>
        </div>
      </form>
    </div>
  );
}

function SimilarRequirementPrompt({
  items,
  isChecking,
  aiEnhanced,
  onOpenExisting,
}: {
  items: SimilarRequirement[];
  isChecking: boolean;
  aiEnhanced: boolean;
  onOpenExisting: (id: string) => void;
}) {
  if (isChecking && !items.length) {
    return <div className="similar-suggestions-box muted">Checking for similar suggestions...</div>;
  }
  if (!items.length) {
    return null;
  }

  const hasHighSimilarity = items.some((item) => item.is_high_confidence);
  return (
    <section className={`similar-suggestions-box ${hasHighSimilarity ? "strong" : ""}`}>
      <div className="similar-suggestions-header">
        <div>
          <strong>{hasHighSimilarity ? "Similar suggestions found" : "Related suggestions"}</strong>
          <span>{aiEnhanced ? "AI confidence included" : "Text similarity match"}</span>
        </div>
      </div>
      <div className="similar-suggestions-list">
        {items.map((item) => (
          <button key={item.id} type="button" className="similar-suggestion-item" onClick={() => onOpenExisting(item.id)}>
            <span className="similar-score">{Math.round(item.similarity * 100)}%</span>
            <span className="similar-copy">
              <strong>POST-{item.number}: {item.title}</strong>
              <small>{item.reason || `${item.votes_count} ${item.votes_count === 1 ? "vote" : "votes"}`}</small>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

function SuggestionDetail({
  item,
  comments,
  isBusy,
  onClose,
  onVote,
  onStatusChange,
  onArchive,
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
              {canWrite ? (
                <form className="comment-form" onSubmit={handleSubmit}>
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
              ) : (
                <p className="comment-empty">Sign in with Feishu to join the discussion.</p>
              )}
            </section>
          </article>

          <aside className="detail-sidebar">
            <button className="big-vote-button" type="button" onClick={() => onVote(item.id)}>
              <span>^</span>
              <strong>{item.vote_count}</strong>
              <small>{item.has_voted ? "voted" : item.vote_count === 1 ? "vote" : "votes"}</small>
            </button>
            {isAdmin ? (
              <div className="admin-controls">
                <label className="status-control">
                  <span>Status</span>
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
                  Archive suggestion
                </button>
              </div>
            ) : null}
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

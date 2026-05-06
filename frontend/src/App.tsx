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
    label: "待收集",
    tone: "neutral",
    response: "这个建议正在收集投票和讨论。",
  },
  approved: {
    label: "已计划",
    tone: "info",
    response: "这个建议已有足够反馈，已进入规划。",
  },
  in_progress: {
    label: "进行中",
    tone: "warning",
    response: "团队正在处理这个建议。",
  },
  done: {
    label: "已完成",
    tone: "success",
    response: "这个建议已经上线或解决。",
  },
  rejected: {
    label: "暂不采纳",
    tone: "danger",
    response: "这个建议暂不符合当前产品方向。",
  },
};

const statusOrder: RequirementStatus[] = ["backlog", "approved", "in_progress", "done", "rejected"];

const filterOptions: Array<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "backlog", label: "待收集" },
  { value: "approved", label: "已计划" },
  { value: "in_progress", label: "进行中" },
  { value: "done", label: "已完成" },
  { value: "rejected", label: "暂不采纳" },
];

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" }).format(new Date(value));
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
  const [notice, setNotice] = useState("正在加载建议...");
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

  const totalVotes = useMemo(() => {
    return items.reduce((total, item) => total + item.vote_count, 0);
  }, [items]);

  async function loadRequirements() {
    const data = await fetchRequirements();
    setItems(data.items);
    setNotice("");
  }

  async function loadCurrentUser() {
    try {
      setCurrentUser(await fetchCurrentUser());
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setCurrentUser(null);
        return;
      }
      setNotice(error instanceof Error ? error.message : "无法加载当前用户。");
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
        setNotice("已通过飞书登录。");
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
    setNotice(`请先通过飞书登录后再${action}。`);
    return false;
  }

  async function handleLogout() {
    setIsBusy(true);
    try {
      await logoutCurrentUser();
      setCurrentUser(null);
      setNotice("已退出登录，仍可继续浏览。");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "退出登录失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCreate(payload: { title: string; description: string }) {
    if (!requireLogin("提交建议")) {
      throw new Error("需要先登录。");
    }
    setIsBusy(true);
    try {
      await createRequirement(payload);
      setNotice("建议已提交。");
      setIsComposerOpen(false);
      await loadRequirements();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "建议提交失败。");
      throw error;
    } finally {
      setIsBusy(false);
    }
  }

  async function handleVote(requirementId: string) {
    if (!requireLogin("投票")) {
      return;
    }
    setIsBusy(true);
    try {
      await voteRequirement(requirementId);
      setNotice("投票已记录。");
      await loadRequirements();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "投票失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleStatusChange(requirementId: string, status: RequirementStatus) {
    if (!isAdmin) {
      setNotice("只有管理员可以修改状态。");
      return;
    }
    setIsBusy(true);
    try {
      await updateRequirementStatus(requirementId, { status });
      setNotice(`状态已改为${statusMeta[status].label}。`);
      await loadRequirements();
    } finally {
      setIsBusy(false);
    }
  }

  async function handleArchive(requirementId: string) {
    if (!isAdmin) {
      setNotice("只有管理员可以归档建议。");
      return;
    }
    setIsBusy(true);
    try {
      await archiveRequirement(requirementId);
      setSelectedId(null);
      setNotice("建议已归档。");
      await loadRequirements();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "归档失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleComment(requirementId: string, payload: { body: string }) {
    if (!requireLogin("评论")) {
      return;
    }
    setIsBusy(true);
    try {
      await createComment(requirementId, payload);
      const data = await fetchComments(requirementId);
      setComments((current) => ({ ...current, [requirementId]: data.items }));
      setNotice("评论已发布。");
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

      {notice ? <div className="app-toast" role="status">{notice}</div> : null}

      <section className="home-layout">
        <aside className="welcome-column">
          <p className="eyebrow">需求投票</p>
          <h1>分享反馈，投出最重要的需求。</h1>
          <p className="welcome-copy">集中收集想法、讨论优先级，让产品决策更透明。</p>
          <div className="welcome-metrics" aria-label="需求概览">
            <div>
              <strong>{items.length}</strong>
              <span>建议</span>
            </div>
            <div>
              <strong>{totalVotes}</strong>
              <span>投票</span>
            </div>
            <div>
              <strong>{counts.in_progress ?? 0}</strong>
              <span>进行中</span>
            </div>
          </div>
          <div className="welcome-status-card">
            <span>当前看板</span>
            <strong>{counts.backlog ?? 0} 个待收集，{counts.approved ?? 0} 个已计划</strong>
          </div>
        </aside>

        <section className="suggestions-column">
          <button
            className="new-suggestion-button"
            type="button"
            onClick={() => {
              if (requireLogin("提交建议")) {
                setIsComposerOpen(true);
              }
            }}
          >
            <span className="plus-icon">+</span>
            <span>你希望接下来做什么？</span>
          </button>

          <SuggestionBoard
            items={visibleItems}
            query={query}
            statusFilter={statusFilter}
            sortMode={sortMode}
            counts={counts}
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
      <div className="brand-mark" aria-label="需求投票">
        <span>需</span>
        <strong>需求投票</strong>
      </div>
      <div className="auth-controls">
        {currentUser ? (
          <>
            <div className="user-pill">
              <strong>{currentUser.name}</strong>
              <span>{currentUser.role === "admin" ? "管理员" : "成员"}</span>
            </div>
            <button className="secondary-button" type="button" onClick={onLogout} disabled={isBusy}>
              退出登录
            </button>
          </>
        ) : (
          <button className="primary-button" type="button" onClick={onLogin} disabled={isAuthLoading}>
            {isAuthLoading ? "检查登录中..." : "飞书登录"}
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
          <SuggestionListItem key={item.id} item={item} onSelect={onSelect} onVote={onVote} canWrite={canWrite} />
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
      setDraftNotice("请至少输入 20 个字，让 AI 能理解你的想法。");
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
      setDraftNotice("AI 已生成标题和描述，你可以继续调整。");
    } catch (error) {
      setDraftNotice(error instanceof Error ? error.message : "AI 生成失败，请稍后再试。");
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
      nextFieldErrors.title = "标题至少需要 3 个字。";
    }
    if (!trimmedDescription) {
      nextFieldErrors.description = "请填写描述。";
    }

    setFieldErrors(nextFieldErrors);
    if (Object.keys(nextFieldErrors).length > 0) {
      setSubmitError("请先修正标出的内容。");
      return;
    }

    if (hasHighSimilarity && !submitConfirmed) {
      setSubmitConfirmed(true);
      setSubmitError("发现相似建议。请先查看，或再次点击继续提交。");
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

      setSubmitError(error instanceof Error ? error.message : "建议提交失败。");
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <form className="modal-panel composer-panel" onSubmit={handleSubmit}>
        <div className="modal-header">
          <div>
            <p className="eyebrow">新建议</p>
            <h2>分享反馈</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="关闭">
            x
          </button>
        </div>
        <section className="ai-draft-box" aria-label="AI 建议草稿">
          <label>
            <span>先简单描述你的想法</span>
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
              {isDrafting ? "AI 生成中..." : "用 AI 生成建议"}
            </button>
            <small className={isDraftError ? "field-error" : "field-hint"}>
              {draftNotice || "AI 会根据你的描述生成标题和详细说明。"}
            </small>
          </div>
        </section>
        <label>
          <span>标题</span>
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
            {fieldErrors.title ?? "至少 3 个字，让别人能快速理解这个想法。"}
          </small>
        </label>
        <label>
          <span>描述</span>
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
            {fieldErrors.description ?? "补充足够细节，方便团队判断需求。"}
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
            取消
          </button>
          <button className="primary-button" type="submit" disabled={isBusy}>
            {isBusy ? "提交中..." : hasHighSimilarity && !submitConfirmed ? "查看相似建议" : submitConfirmed ? "仍然提交" : "提交建议"}
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
    return <div className="similar-suggestions-box muted">正在检查相似建议...</div>;
  }
  if (!items.length) {
    return null;
  }

  const hasHighSimilarity = items.some((item) => item.is_high_confidence);
  return (
    <section className={`similar-suggestions-box ${hasHighSimilarity ? "strong" : ""}`}>
      <div className="similar-suggestions-header">
        <div>
          <strong>{hasHighSimilarity ? "发现相似建议" : "相关建议"}</strong>
          <span>{aiEnhanced ? "已结合 AI 判断" : "文本相似度匹配"}</span>
        </div>
      </div>
      <div className="similar-suggestions-list">
        {items.map((item) => (
          <button key={item.id} type="button" className="similar-suggestion-item" onClick={() => onOpenExisting(item.id)}>
            <span className="similar-score">{Math.round(item.similarity * 100)}%</span>
            <span className="similar-copy">
              <strong>POST-{item.number}: {item.title}</strong>
              <small>{item.reason || `${item.votes_count} 票`}</small>
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
            <p className="detail-description">{item.description}</p>

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
                  归档建议
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

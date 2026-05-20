import { FormEvent, useEffect, useMemo, useState } from "react";

import { AUTH_EXPIRED_EVENT, ApiError, startFeishuBrowserLogin } from "./api/client";
import { RichContentEditor, RichContentPreview } from "./features/rich-content/RichContentEditor";
import { TaskPage } from "./features/tasks/TaskPage";
import {
  archiveRequirement,
  convertRequirementToTask,
  createComment,
  createRequirement,
  createTag,
  draftRequirementWithAi,
  exchangeFeishuClientCode,
  fetchComments,
  fetchCurrentUser,
  fetchRequirements,
  fetchTags,
  findSimilarRequirements,
  logoutCurrentUser,
  updateRequirementStatus,
  voteRequirement,
} from "./features/requirements/api";
import { fetchTaskAssignees } from "./features/tasks/api";
import type { CommentItem, CurrentUser, Requirement, RequirementStatus, RequirementTag, SimilarRequirement } from "./types/requirement";

type SortMode = "popular" | "newest" | "recent";
type StatusFilter = "all" | RequirementStatus;
type AppView = "requirements" | "tasks";

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
const tagColors = ["#2f75d6", "#1f8a5b", "#b83245", "#8f5bd6", "#d68b2f"];

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" }).format(new Date(value));
}

function normalize(value: string) {
  return value.trim().toLowerCase();
}

type ComposerField = "title" | "description";
type ComposerStep = "idea" | "draft";

export default function App() {
  const [items, setItems] = useState<Requirement[]>([]);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const [sortMode, setSortMode] = useState<SortMode>("popular");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [comments, setComments] = useState<Record<string, CommentItem[]>>({});
  const [tags, setTags] = useState<RequirementTag[]>([]);
  const [notice, setNotice] = useState("正在加载建议...");
  const [isComposerOpen, setIsComposerOpen] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(true);
  const [conversionItem, setConversionItem] = useState<Requirement | null>(null);
  const [activeView, setActiveView] = useState<AppView>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("view") === "tasks" ? "tasks" : "requirements";
  });

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
        return normalize(`${item.title} ${item.description} ${item.req_id} ${item.tags.map((tag) => tag.name).join(" ")}`).includes(keyword);
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

  async function loadTags() {
    const data = await fetchTags();
    setTags(data.items);
  }

  async function loadCurrentUser(showExpiredNotice = false) {
    try {
      setCurrentUser(await fetchCurrentUser());
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        if (showExpiredNotice) {
          setNotice("登录已过期，请重新登录。");
        }
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
    loadTags().catch((error: Error) => setNotice(error.message));
    loadCurrentUser();
  }, []);

  useEffect(() => {
    if (activeView !== "requirements") {
      return;
    }
    loadRequirements().catch((error: Error) => setNotice(error.message));
    loadTags().catch((error: Error) => setNotice(error.message));
  }, [activeView]);

  useEffect(() => {
    if (!currentUser) {
      return;
    }

    const handleAuthExpired = () => {
      setCurrentUser(null);
      setNotice("登录已过期，请重新登录。");
    };

    const handleFocus = () => {
      loadCurrentUser(true);
    };

    window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
    window.addEventListener("focus", handleFocus);
    const intervalId = window.setInterval(() => loadCurrentUser(true), 5 * 60 * 1000);

    return () => {
      window.removeEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
      window.removeEventListener("focus", handleFocus);
      window.clearInterval(intervalId);
    };
  }, [currentUser]);

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

  async function handleCreate(payload: { title: string; description: string; tags: string[] }) {
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

  async function handleCreateTag(name: string) {
    const color = tagColors[Math.floor(Math.random() * tagColors.length)];
    await createTag({ name, color });
    const data = await fetchTags();
    setTags(data.items);
    return data.items;
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
    const item = items.find((entry) => entry.id === requirementId);
    if (status === "in_progress" && item && !item.linked_task) {
      setConversionItem(item);
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

  async function handleConvertToTask(payload: {
    title: string;
    description_markdown: string;
    assignee_user_id: string | null;
    labels: string[];
  }) {
    if (!conversionItem) {
      return;
    }
    setIsBusy(true);
    try {
      const result = await convertRequirementToTask(conversionItem.id, payload);
      setNotice(`已创建 TASK-${result.task.number}，需求已进入处理中。`);
      setConversionItem(null);
      await loadRequirements();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "转为任务失败。");
      throw error;
    } finally {
      setIsBusy(false);
    }
  }

  function openLinkedTask(taskId: string) {
    const params = new URLSearchParams(window.location.search);
    params.set("view", "tasks");
    params.set("task", taskId);
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
    setActiveView("tasks");
    setSelectedId(null);
  }

  async function handleArchive(requirementId: string) {
    if (!isAdmin) {
      setNotice("只有管理员可以删除建议。");
      return;
    }
    if (!window.confirm("确定删除这条建议吗？删除后前台列表将不再显示。")) {
      return;
    }
    setIsBusy(true);
    try {
      await archiveRequirement(requirementId);
      setSelectedId(null);
      setNotice("建议已删除。");
      await loadRequirements();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "删除失败。");
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

  if (activeView === "tasks") {
    return (
      <main className="app-shell">
        <Header
          currentUser={currentUser}
          isAuthLoading={isAuthLoading}
          isBusy={isBusy}
          onLogin={startFeishuBrowserLogin}
          onLogout={handleLogout}
        />
        <ViewSwitcher activeView={activeView} onChange={setActiveView} />
        {notice ? <div className="app-toast" role="status">{notice}</div> : null}
        <TaskPage currentUser={currentUser} />
      </main>
    );
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

      <ViewSwitcher activeView={activeView} onChange={setActiveView} />

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
          tags={tags}
          onClose={() => setIsComposerOpen(false)}
          onOpenExisting={(id) => {
            setIsComposerOpen(false);
            setSelectedId(id);
          }}
          onCreateTag={handleCreateTag}
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
          onOpenTask={openLinkedTask}
          onComment={handleComment}
          canWrite={Boolean(currentUser)}
          isAdmin={isAdmin}
        />
      ) : null}

      {conversionItem ? (
        <RequirementTaskModal
          item={conversionItem}
          isBusy={isBusy}
          onClose={() => setConversionItem(null)}
          onSubmit={handleConvertToTask}
        />
      ) : null}
    </main>
  );
}

function ViewSwitcher({
  activeView,
  onChange,
}: {
  activeView: AppView;
  onChange: (view: AppView) => void;
}) {
  return (
    <nav className="view-switcher" aria-label="功能切换">
      <button
        className={activeView === "requirements" ? "active" : ""}
        type="button"
        onClick={() => onChange("requirements")}
      >
        需求投票
      </button>
      <button className={activeView === "tasks" ? "active" : ""} type="button" onClick={() => onChange("tasks")}>
        任务管理
      </button>
    </nav>
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

function SuggestionComposer({
  isBusy,
  tags,
  onClose,
  onOpenExisting,
  onCreateTag,
  onSubmit,
}: {
  isBusy: boolean;
  tags: RequirementTag[];
  onClose: () => void;
  onOpenExisting: (id: string) => void;
  onCreateTag: (name: string) => Promise<RequirementTag[]>;
  onSubmit: (payload: { title: string; description: string; tags: string[] }) => Promise<void>;
}) {
  const copy = {
    ideaTooShort: "\u8bf7\u81f3\u5c11\u8f93\u5165 20 \u4e2a\u5b57\uff0c\u8ba9 AI \u80fd\u7406\u89e3\u4f60\u7684\u60f3\u6cd5\u3002",
    replaceDraft: "\u91cd\u65b0\u751f\u6210\u4f1a\u8986\u76d6\u5f53\u524d\u6807\u9898\u548c\u63cf\u8ff0\uff0c\u786e\u5b9a\u7ee7\u7eed\u5417\uff1f",
    draftReady: "AI \u5df2\u6574\u7406\u597d\u8349\u7a3f\uff0c\u4f60\u53ef\u4ee5\u7ee7\u7eed\u4fee\u6539\u3002",
    draftFailed: "AI \u751f\u6210\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5\u3002",
    titleTooShort: "\u6807\u9898\u81f3\u5c11 3 \u4e2a\u5b57\u3002",
    descriptionRequired: "\u8bf7\u8865\u5145\u9700\u6c42\u63cf\u8ff0\u3002",
    fixFields: "\u8bf7\u5148\u4fee\u6b63\u6807\u51fa\u7684\u5185\u5bb9\u3002",
    similarFound: "\u53d1\u73b0\u7c7b\u4f3c\u9700\u6c42\u3002\u4f60\u53ef\u4ee5\u5148\u67e5\u770b\u5df2\u6709\u9700\u6c42\uff0c\u6216\u518d\u6b21\u70b9\u51fb\u63d0\u4ea4\u3002",
    similarCheckFailed: "\u67e5\u91cd\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5\u3002",
    noSimilarFound: "\u672a\u53d1\u73b0\u660e\u663e\u91cd\u590d\u9700\u6c42\u3002",
    submitFailed: "\u5efa\u8bae\u63d0\u4ea4\u5931\u8d25\u3002",
    newSuggestion: "\u65b0\u5efa\u8bae",
    ideaTitle: "\u60f3\u63d0\u4ec0\u4e48\u9700\u6c42\uff1f",
    close: "\u5173\u95ed",
    ideaLabel: "\u5148\u7528\u4e00\u53e5\u8bdd\u8bf4\u6e05\u60f3\u6cd5",
    ideaPlaceholder: "\u4f8b\u5982\uff1a\u5e0c\u671b\u53ef\u4ee5\u6309\u90e8\u95e8\u7b5b\u9009\u6295\u7968\u7ed3\u679c\uff0c\u65b9\u4fbf\u5224\u65ad\u4e0d\u540c\u56e2\u961f\u6700\u5173\u5fc3\u4ec0\u4e48",
    ideaHint: "\u4e0d\u7528\u60f3\u6807\u9898\u548c\u683c\u5f0f\uff0cAI \u4f1a\u5e2e\u4f60\u6574\u7406\u6210\u53ef\u63d0\u4ea4\u7684\u5efa\u8bae\u3002",
    manualStart: "\u76f4\u63a5\u624b\u52a8\u586b\u5199",
    aiWorking: "AI \u6b63\u5728\u6574\u7406...",
    aiDraft: "AI \u5e2e\u6211\u6574\u7406",
    confirmContent: "\u786e\u8ba4\u5185\u5bb9",
    draftTitle: "\u7f16\u8f91\u5efa\u8bae\u8349\u7a3f",
    originalIdea: "\u539f\u59cb\u60f3\u6cd5",
    regenerating: "\u91cd\u65b0\u6574\u7406\u4e2d...",
    regenerate: "\u91cd\u65b0\u751f\u6210",
    title: "\u6807\u9898",
    titleHint: "\u81f3\u5c11 3 \u4e2a\u5b57\uff0c\u8ba9\u522b\u4eba\u80fd\u5feb\u901f\u7406\u89e3\u8fd9\u4e2a\u60f3\u6cd5\u3002",
    description: "\u63cf\u8ff0",
    descriptionHint: "\u8865\u5145\u573a\u666f\u3001\u95ee\u9898\u548c\u671f\u671b\u7ed3\u679c\uff0c\u65b9\u4fbf\u56e2\u961f\u5224\u65ad\u9700\u6c42\u3002",
    tags: "\u6807\u7b7e",
    newTag: "\u65b0\u589e\u6807\u7b7e",
    tagPlaceholder: "\u8f93\u5165\u65b0\u6807\u7b7e",
    tagCreateFailed: "\u6807\u7b7e\u521b\u5efa\u5931\u8d25\u3002",
    back: "\u8fd4\u56de",
    submitting: "\u63d0\u4ea4\u4e2d...",
    confirmSimilar: "\u786e\u8ba4\u7c7b\u4f3c\u9700\u6c42",
    checkSimilar: "\u624b\u52a8\u67e5\u91cd",
    checkingSimilar: "\u67e5\u91cd\u4e2d...",
    checkAgain: "\u91cd\u65b0\u67e5\u91cd",
    submitAnyway: "\u4ecd\u7136\u63d0\u4ea4",
    submit: "\u63d0\u4ea4\u5efa\u8bae",
  };
  const [step, setStep] = useState<ComposerStep>("idea");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [newTag, setNewTag] = useState("");
  const [tagError, setTagError] = useState("");
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
  const canRegenerate = Boolean(roughIdea.trim());

  async function handleDraft() {
    const trimmedIdea = roughIdea.trim();
    if (trimmedIdea.length < 20) {
      setDraftNotice(copy.ideaTooShort);
      setIsDraftError(true);
      return;
    }

    if (step === "draft" && (title.trim() || description.trim())) {
      const shouldReplace = window.confirm(copy.replaceDraft);
      if (!shouldReplace) {
        return;
      }
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
      setDraftNotice(copy.draftReady);
      setStep("draft");
    } catch (error) {
      setDraftNotice(error instanceof Error ? error.message : copy.draftFailed);
      setIsDraftError(true);
    } finally {
      setIsDrafting(false);
    }
  }

  function handleManualStart() {
    setStep("draft");
    setSubmitError("");
    setDraftNotice("");
    setIsDraftError(false);
    setFieldErrors({});
  }

  function handleBackToIdea() {
    setStep("idea");
    setSubmitError("");
    setFieldErrors({});
    setSimilarItems([]);
    setSimilarAiEnhanced(false);
    setSubmitConfirmed(false);
  }

  async function handleSimilarityCheck() {
    const trimmedTitle = title.trim();
    const trimmedDescription = description.trim();
    const nextFieldErrors: Partial<Record<ComposerField, string>> = {};

    if (trimmedTitle.length < 3) {
      nextFieldErrors.title = copy.titleTooShort;
    }
    if (!trimmedDescription) {
      nextFieldErrors.description = copy.descriptionRequired;
    }

    setFieldErrors(nextFieldErrors);
    if (Object.keys(nextFieldErrors).length > 0) {
      setSubmitError(copy.fixFields);
      return;
    }

    setIsCheckingSimilar(true);
    setSubmitConfirmed(false);
    setSubmitError("");
    try {
      const data = await findSimilarRequirements({ title: trimmedTitle, description: trimmedDescription, limit: 3 });
      setSimilarItems(data.items);
      setSimilarAiEnhanced(data.ai_enhanced);
      setSubmitError(data.items.length ? "" : copy.noSimilarFound);
    } catch (error) {
      setSimilarItems([]);
      setSimilarAiEnhanced(false);
      setSubmitError(error instanceof Error ? error.message : copy.similarCheckFailed);
    } finally {
      setIsCheckingSimilar(false);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const nextFieldErrors: Partial<Record<ComposerField, string>> = {};
    const trimmedTitle = title.trim();
    const trimmedDescription = description.trim();

    if (trimmedTitle.length < 3) {
      nextFieldErrors.title = copy.titleTooShort;
    }
    if (!trimmedDescription) {
      nextFieldErrors.description = copy.descriptionRequired;
    }

    setFieldErrors(nextFieldErrors);
    if (Object.keys(nextFieldErrors).length > 0) {
      setSubmitError(copy.fixFields);
      return;
    }

    if (hasHighSimilarity && !submitConfirmed) {
      setSubmitConfirmed(true);
      setSubmitError(copy.similarFound);
      return;
    }

    setSubmitError("");

    try {
      await onSubmit({
        title: trimmedTitle,
        description: trimmedDescription,
        tags: selectedTags,
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

      setSubmitError(error instanceof Error ? error.message : copy.submitFailed);
    }
  }

  if (step === "idea") {
    return (
      <div className="modal-backdrop" role="presentation">
        <form
          className="modal-panel composer-panel idea-composer-panel"
          onSubmit={(event) => {
            event.preventDefault();
            handleDraft();
          }}
        >
          <div className="modal-header">
            <div>
              <p className="eyebrow">{copy.newSuggestion}</p>
              <h2>{copy.ideaTitle}</h2>
            </div>
            <button className="icon-button" type="button" onClick={onClose} aria-label={copy.close}>
              x
            </button>
          </div>

          <section className="idea-capture-box">
            <label>
              <span>{copy.ideaLabel}</span>
              <textarea
                value={roughIdea}
                onChange={(event) => {
                  setRoughIdea(event.target.value);
                  setDraftNotice("");
                  setIsDraftError(false);
                }}
                rows={6}
                maxLength={12000}
                placeholder={copy.ideaPlaceholder}
                autoFocus
              />
            </label>
            <small className={isDraftError ? "field-error" : "field-hint"}>
              {draftNotice || copy.ideaHint}
            </small>
          </section>

          <div className="modal-actions idea-actions">
            <button className="secondary-button" type="button" onClick={handleManualStart}>
              {copy.manualStart}
            </button>
            <button className="primary-button" type="submit" disabled={isDrafting || isBusy}>
              {isDrafting ? copy.aiWorking : copy.aiDraft}
            </button>
          </div>
        </form>
      </div>
    );
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <form className="modal-panel composer-panel" onSubmit={handleSubmit}>
        <div className="modal-header">
          <div>
            <p className="eyebrow">{copy.confirmContent}</p>
            <h2>{copy.draftTitle}</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label={copy.close}>
            x
          </button>
        </div>

        {canRegenerate ? (
          <section className="draft-source-box" aria-label={copy.originalIdea}>
            <div>
              <span>{copy.originalIdea}</span>
              <p>{roughIdea.trim()}</p>
            </div>
            <button className="secondary-button" type="button" onClick={handleDraft} disabled={isDrafting || isBusy}>
              {isDrafting ? copy.regenerating : copy.regenerate}
            </button>
          </section>
        ) : null}

        {draftNotice && !isDraftError ? <div className="draft-notice">{draftNotice}</div> : null}

        <label>
          <span>{copy.title}</span>
          <input
            value={title}
            onChange={(event) => {
              setTitle(event.target.value);
              setSubmitConfirmed(false);
              setSimilarItems([]);
              setSimilarAiEnhanced(false);
              setFieldErrors((current) => ({ ...current, title: undefined }));
              setSubmitError("");
            }}
            maxLength={120}
            minLength={3}
            required
            aria-invalid={Boolean(fieldErrors.title)}
            className={fieldErrors.title ? "input-error" : ""}
            autoFocus={!canRegenerate}
          />
          <small className={fieldErrors.title ? "field-error" : "field-hint"}>
            {fieldErrors.title ?? copy.titleHint}
          </small>
        </label>
        <div className="rich-field">
          <span>{copy.description}</span>
          <RichContentEditor
            value={description}
            onChange={(nextValue) => {
              setDescription(nextValue);
              setSubmitConfirmed(false);
              setSimilarItems([]);
              setSimilarAiEnhanced(false);
              setFieldErrors((current) => ({ ...current, description: undefined }));
              setSubmitError("");
            }}
            minRows={7}
          />
          <small className={fieldErrors.description ? "field-error" : "field-hint"}>
            {fieldErrors.description ?? copy.descriptionHint}
          </small>
        </div>
        <label>
          <span>{copy.tags}</span>
          <div className="label-picker">
            {tags.map((tag) => (
              <label key={tag.slug} className="label-choice">
                <input
                  type="checkbox"
                  checked={selectedTags.includes(tag.name)}
                  onChange={(event) => {
                    setSelectedTags((current) =>
                      event.target.checked ? [...current, tag.name] : current.filter((name) => name !== tag.name),
                    );
                  }}
                />
                <span className="label-dot" style={{ backgroundColor: tag.color }} />
                {tag.name}
              </label>
            ))}
          </div>
          <div className="new-label-row">
            <input
              value={newTag}
              onChange={(event) => {
                setNewTag(event.target.value);
                setTagError("");
              }}
              placeholder={copy.tagPlaceholder}
            />
            <button
              className="secondary-button"
              type="button"
              onClick={() => {
                const name = newTag.trim();
                if (!name) return;
                onCreateTag(name)
                  .then(() => {
                    setSelectedTags((current) => [...new Set([...current, name])]);
                    setNewTag("");
                  })
                  .catch((error: Error) => setTagError(error.message || copy.tagCreateFailed));
              }}
            >
              {copy.newTag}
            </button>
          </div>
          {tagError ? <small className="field-error">{tagError}</small> : null}
        </label>
        <div className="similar-check-actions">
          <button className="secondary-button" type="button" onClick={handleSimilarityCheck} disabled={isCheckingSimilar || isBusy}>
            {isCheckingSimilar ? copy.checkingSimilar : similarItems.length ? copy.checkAgain : copy.checkSimilar}
          </button>
        </div>
        <SimilarRequirementPrompt
          items={similarItems}
          isChecking={isCheckingSimilar}
          aiEnhanced={similarAiEnhanced}
          onOpenExisting={onOpenExisting}
        />
        {submitError ? <div className="form-error">{submitError}</div> : null}
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={handleBackToIdea}>
            {copy.back}
          </button>
          <button className="primary-button" type="submit" disabled={isBusy}>
            {isBusy ? copy.submitting : hasHighSimilarity && !submitConfirmed ? copy.confirmSimilar : submitConfirmed ? copy.submitAnyway : copy.submit}
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
  onOpenTask,
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
  onOpenTask: (taskId: string) => void;
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
                  删除建议
                </button>
              </div>
            ) : null}
          </aside>
        </div>
      </section>
    </div>
  );
}

function RequirementTaskModal({
  item,
  isBusy,
  onClose,
  onSubmit,
}: {
  item: Requirement;
  isBusy: boolean;
  onClose: () => void;
  onSubmit: (payload: {
    title: string;
    description_markdown: string;
    assignee_user_id: string | null;
    labels: string[];
  }) => Promise<void>;
}) {
  const defaultDescription = [
    item.description,
    "",
    `来源需求：${item.req_id}`,
    `当前票数：${item.vote_count}`,
    `提交人：${item.creator_name}`,
    `链接：/?post=${item.id}`,
  ].join("\n");
  const [title, setTitle] = useState(item.title);
  const [description, setDescription] = useState(defaultDescription);
  const [assigneeId, setAssigneeId] = useState("");
  const [labels, setLabels] = useState("需求转入");
  const [assignees, setAssignees] = useState<CurrentUser[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchTaskAssignees()
      .then((data) => setAssignees(data.items))
      .catch((err: Error) => setError(err.message));
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await onSubmit({
        title: title.trim(),
        description_markdown: description,
        assignee_user_id: assigneeId || null,
        labels: labels
          .split(",")
          .map((label) => label.trim())
          .filter(Boolean),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建任务失败。");
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <form className="modal-panel conversion-panel" onSubmit={handleSubmit}>
        <div className="modal-header">
          <div>
            <p className="eyebrow">转为任务</p>
            <h2>{item.req_id}</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="关闭">
            x
          </button>
        </div>
        <div className="conversion-source">
          <strong>{item.title}</strong>
          <span>{item.vote_count} 票 · {item.creator_name}</span>
        </div>
        <label>
          <span>任务标题</span>
          <input value={title} onChange={(event) => setTitle(event.target.value)} minLength={3} maxLength={160} required />
        </label>
        <label>
          <span>负责人</span>
          <select value={assigneeId} onChange={(event) => setAssigneeId(event.target.value)}>
            <option value="">暂不分配</option>
            {assignees.map((user) => (
              <option key={user.id} value={user.id}>{user.name}</option>
            ))}
          </select>
        </label>
        <label>
          <span>标签</span>
          <input value={labels} onChange={(event) => setLabels(event.target.value)} placeholder="需求转入, 前端" />
        </label>
        <div className="rich-field">
          <span>描述</span>
          <RichContentEditor value={description} onChange={setDescription} minRows={9} />
        </div>
        {error ? <div className="form-error">{error}</div> : null}
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={onClose}>取消</button>
          <button className="primary-button" type="submit" disabled={isBusy}>
            {isBusy ? "创建中..." : "创建任务并开始处理"}
          </button>
        </div>
      </form>
    </div>
  );
}

function StatusLozenge({ status }: { status: RequirementStatus }) {
  const meta = statusMeta[status];
  return <span className={`status-lozenge status-${meta.tone}`}>{meta.label}</span>;
}

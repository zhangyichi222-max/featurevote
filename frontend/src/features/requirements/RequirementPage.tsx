import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import type { CommentItem, CurrentUser, Requirement, RequirementStatus, RequirementTag } from "../../types/requirement";
import { archiveRequirement, convertRequirementToTask, createComment, createRequirement, createTag, fetchComments, fetchRequirements, fetchTags, updateRequirementStatus, voteRequirement } from "./api";
import { RequirementBoard } from "./RequirementBoard";
import { RequirementComposer } from "./RequirementComposer";
import { RequirementDetail } from "./RequirementDetail";
import { RequirementTaskModal } from "./RequirementTaskModal";
import type { SortMode, StatusFilter } from "./constants";
import { statusMeta, statusOrder, tagColors } from "./constants";
import { normalize } from "./utils";

export function RequirementPage({ currentUser, isBusy, setIsBusy, setNotice, onOpenTasks }: { currentUser: CurrentUser | null; isBusy: boolean; setIsBusy: (value: boolean) => void; setNotice: (value: string) => void; onOpenTasks: () => void; }) {
  const [items, setItems] = useState<Requirement[]>([]);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const [sortMode, setSortMode] = useState<SortMode>("popular");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [comments, setComments] = useState<Record<string, CommentItem[]>>({});
  const [tags, setTags] = useState<RequirementTag[]>([]);
  const [isComposerOpen, setIsComposerOpen] = useState(false);
  const [conversionItem, setConversionItem] = useState<Requirement | null>(null);
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

  useEffect(() => {
    loadRequirements().catch((error: Error) => setNotice(error.message));
    loadTags().catch((error: Error) => setNotice(error.message));
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
    onOpenTasks();
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

  return (
    <>
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

          <RequirementBoard
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
        <RequirementComposer
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
        <RequirementDetail
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
    </>
  );
}


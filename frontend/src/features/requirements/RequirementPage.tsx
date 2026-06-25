import { useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "../../api/client";
import type { CurrentUser, Requirement, RequirementTag } from "../../types/requirement";
import { archiveRequirement, convertRequirementToTask, createRequirement, createTag, fetchRequirements, fetchTags, updateRequirement, voteRequirement } from "./api";
import { RequirementBoard, RequirementFilters } from "./RequirementBoard";
import { RequirementComposer } from "./RequirementComposer";
import { RequirementDetail } from "./RequirementDetail";
import { RequirementEditor } from "./RequirementEditor";
import { RequirementTaskModal } from "./RequirementTaskModal";
import type { SortMode } from "./constants";
import { tagColors } from "./constants";

const PAGE_SIZE = 20;

function readListState() {
  const params = new URLSearchParams(window.location.search);
  const requestedPage = Number.parseInt(params.get("page") ?? "1", 10);
  const requestedSort = params.get("sort");
  return {
    page: Number.isFinite(requestedPage) && requestedPage > 0 ? requestedPage : 1,
    query: params.get("query") ?? "",
    sortMode: requestedSort === "recent" || requestedSort === "newest" ? requestedSort : "popular" as SortMode,
    label: params.get("label") ?? "",
  };
}

export function RequirementPage({ currentUser, isBusy, setIsBusy, setNotice }: { currentUser: CurrentUser | null; isBusy: boolean; setIsBusy: (value: boolean) => void; setNotice: (value: string) => void; }) {
  const initialListState = useMemo(readListState, []);
  const [items, setItems] = useState<Requirement[]>([]);
  const [query, setQuery] = useState(initialListState.query);
  const [debouncedQuery, setDebouncedQuery] = useState(initialListState.query);
  const [sortMode, setSortMode] = useState<SortMode>(initialListState.sortMode);
  const [label, setLabel] = useState(initialListState.label);
  const [page, setPage] = useState(initialListState.page);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tags, setTags] = useState<RequirementTag[]>([]);
  const [isComposerOpen, setIsComposerOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<Requirement | null>(null);
  const [conversionItem, setConversionItem] = useState<Requirement | null>(null);
  const requestSequence = useRef(0);

  const selectedItem = useMemo(
    () => items.find((item) => item.id === selectedId) ?? null,
    [items, selectedId],
  );

  function writeListState(
    next: { page: number; query: string; sortMode: SortMode; label: string },
    mode: "push" | "replace" = "replace",
  ) {
    const params = new URLSearchParams(window.location.search);
    if (next.page > 1) params.set("page", String(next.page));
    else params.delete("page");
    if (next.query.trim()) params.set("query", next.query);
    else params.delete("query");
    if (next.sortMode !== "popular") params.set("sort", next.sortMode);
    else params.delete("sort");
    if (next.label) params.set("label", next.label);
    else params.delete("label");
    const search = params.toString();
    window.history[mode === "push" ? "pushState" : "replaceState"](
      null,
      "",
      `${window.location.pathname}${search ? `?${search}` : ""}`,
    );
  }

  function updatePage(nextPage: number) {
    if (nextPage < 1 || (totalPages && nextPage > totalPages)) {
      return;
    }
    setPage(nextPage);
    setSelectedId(null);
    writeListState({ page: nextPage, query, sortMode, label }, "push");
  }

  function updateQuery(nextQuery: string) {
    setQuery(nextQuery);
    setPage(1);
    setSelectedId(null);
    writeListState({ page: 1, query: nextQuery, sortMode, label });
  }

  function updateSortMode(nextSort: SortMode) {
    setSortMode(nextSort);
    setPage(1);
    setSelectedId(null);
    writeListState({ page: 1, query, sortMode: nextSort, label }, "push");
  }

  function updateLabel(nextLabel: string) {
    setLabel(nextLabel);
    setPage(1);
    setSelectedId(null);
    writeListState({ page: 1, query, sortMode, label: nextLabel }, "push");
  }

  async function loadRequirements(requestedPage = page) {
    const requestId = ++requestSequence.current;
    const data = await fetchRequirements({
      page: requestedPage,
      pageSize: PAGE_SIZE,
      query: debouncedQuery,
      sort: sortMode,
      label,
    });
    if (requestId !== requestSequence.current) {
      return false;
    }
    const lastAvailablePage = Math.max(1, data.total_pages);
    if (requestedPage > lastAvailablePage) {
      setPage(lastAvailablePage);
      writeListState({ page: lastAvailablePage, query, sortMode, label });
      return false;
    }
    setItems(data.items);
    setTotal(data.total);
    setTotalPages(data.total_pages);
    setSelectedId((current) => current && data.items.some((item) => item.id === current) ? current : null);
    setNotice("");
    return true;
  }

  async function loadTags() {
    const data = await fetchTags();
    setTags(data.items);
  }

  useEffect(() => {
    loadTags().catch((error: Error) => setNotice(error.message));
  }, []);

  useEffect(() => {
    const timerId = window.setTimeout(() => setDebouncedQuery(query), 300);
    return () => window.clearTimeout(timerId);
  }, [query]);

  useEffect(() => {
    loadRequirements().catch((error: Error) => setNotice(error.message));
  }, [debouncedQuery, label, page, sortMode]);

  useEffect(() => {
    const handlePopState = () => {
      const next = readListState();
      setPage(next.page);
      setQuery(next.query);
      setDebouncedQuery(next.query);
      setSortMode(next.sortMode);
      setLabel(next.label);
      setSelectedId(null);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  function requireLogin(action: string) {
    if (currentUser) {
      return true;
    }
    setNotice(`请先通过飞书登录后再${action}。`);
    return false;
  }

  async function handleCreate(payload: { title: string; description: string; tags: string[] }) {
    if (!requireLogin("提交需求草稿")) {
      throw new Error("需要先登录。");
    }
    setIsBusy(true);
    try {
      await createRequirement(payload);
      setNotice("需求草稿已提交。");
      setIsComposerOpen(false);
      if (page !== 1) {
        updatePage(1);
      } else {
        await loadRequirements(1);
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "需求草稿提交失败。");
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

  async function handleEdit(payload: { title: string; description: string; tags: string[] }) {
    if (!editingItem || !requireLogin("编辑需求草稿")) {
      return;
    }
    setIsBusy(true);
    try {
      await updateRequirement(editingItem.id, payload);
      await loadRequirements(page);
      setEditingItem(null);
      setNotice("需求草稿已更新。");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "需求草稿保存失败。");
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
      await loadRequirements(page);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "投票失败。");
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
      setNotice(`已采纳需求草稿并创建 TASK-${result.task.number}。`);
      setConversionItem(null);
      setSelectedId(null);
      await loadRequirements(page);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "采纳并创建任务失败。");
      throw error;
    } finally {
      setIsBusy(false);
    }
  }

  async function handleArchive(requirementId: string) {
    if (!requireLogin("删除需求草稿")) {
      return;
    }
    if (!window.confirm("确定删除这份需求草稿吗？删除后草稿池将不再显示。")) {
      return;
    }
    setIsBusy(true);
    try {
      await archiveRequirement(requirementId);
      setSelectedId(null);
      setNotice("需求草稿已删除。");
      await loadRequirements(page);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "删除失败。");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <>
      <section className="requirement-page">
        <div className="requirement-toolbar">
          <div>
            <p className="eyebrow">需求草稿池</p>
            <h2>待处理草稿</h2>
          </div>
          <button
            className="primary-button"
            type="button"
            onClick={() => {
              if (requireLogin("提交需求草稿")) {
                setIsComposerOpen(true);
              }
            }}
          >
            新建草稿
          </button>
        </div>
        <RequirementFilters
          query={query}
          sortMode={sortMode}
          label={label}
          labels={tags}
          onQueryChange={updateQuery}
          onSortChange={updateSortMode}
          onLabelChange={updateLabel}
        />
        <div className="requirement-layout">
          <RequirementBoard
            items={items}
            selectedItem={selectedItem}
            page={page}
            pageSize={PAGE_SIZE}
            total={total}
            totalPages={totalPages}
            onPageChange={updatePage}
            onSelect={(item) => setSelectedId(item.id)}
            onVote={handleVote}
            canWrite={Boolean(currentUser)}
          />
          <RequirementDetail
            item={selectedItem}
            isBusy={isBusy}
            onVote={handleVote}
            onConvert={setConversionItem}
            onArchive={handleArchive}
            onEdit={setEditingItem}
            canEdit={Boolean(currentUser)}
            canManage={Boolean(currentUser)}
            canViewSources={Boolean(currentUser)}
          />
        </div>
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

      {editingItem ? (
        <RequirementEditor
          item={editingItem}
          tags={tags}
          isBusy={isBusy}
          onClose={() => setEditingItem(null)}
          onCreateTag={handleCreateTag}
          onSave={handleEdit}
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


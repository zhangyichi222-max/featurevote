import { apiClient } from "../../api/client";
import type {
  CurrentUser,
  RequirementListResponse,
  RequirementSourcesResponse,
  SimilarRequirementsResponse,
} from "../../types/requirement";

type PostStatus = "open" | "planned" | "in_progress" | "completed" | "declined" | "duplicate";

type PostItem = {
  id: string;
  number: number;
  slug: string;
  title: string;
  description: string;
  status: PostStatus;
  is_approved: boolean;
  votes_count: number;
  has_voted?: boolean;
  user: { name: string; id: string };
  tags: Array<{ id: string; slug: string; name: string; color: string }>;
  response?: { text: string } | null;
  duplicate_of?: { number: number; title: string } | null;
  linked_task?: { id: string; number: number; title: string; status: string } | null;
  created_at: string;
  updated_at: string;
};

type CurrentUserResponse = {
  user?: CurrentUser | null;
} & Partial<CurrentUser>;

type PostListResponse = {
  items: PostItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export async function fetchRequirements({
  page,
  pageSize = 20,
  query = "",
  sort = "popular",
  label = "",
}: {
  page: number;
  pageSize?: number;
  query?: string;
  sort?: "popular" | "recent" | "newest";
  label?: string;
}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    view: sort === "popular" ? "trending" : sort,
  });
  if (query.trim()) {
    params.set("query", query.trim());
  }
  if (label) {
    params.append("tags", label);
  }
  const data = await apiClient.get<PostListResponse>(`/posts?${params.toString()}`);
  return {
    items: data.items.map((item) => ({
      id: item.id,
      req_id: `POST-${item.number}`,
      title: item.title,
      description: item.description,
      vote_count: item.votes_count,
      has_voted: Boolean(item.has_voted),
      creator_name: item.user.name,
      creator_open_id: item.user.id,
      tags: item.tags.map((tag) => ({
        id: tag.id,
        name: tag.name,
        slug: tag.slug,
        color: tag.color,
      })),
      linked_task: item.linked_task ?? null,
      created_at: item.created_at,
      updated_at: item.updated_at,
    })),
    total: data.total,
    page: data.page,
    page_size: data.page_size,
    total_pages: data.total_pages,
  } satisfies RequirementListResponse;
}

export async function fetchRequirementSources(requirementId: string) {
  return apiClient.get<RequirementSourcesResponse>(`/posts/${requirementId}/sources`);
}

export async function createRequirement(payload: {
  title: string;
  description: string;
  tags?: string[];
}) {
  return apiClient.post<{ id: string }>("/posts", {
    title: payload.title,
    description: payload.description,
    tags: payload.tags ?? [],
  });
}

export async function updateRequirement(
  requirementId: string,
  payload: {
    title?: string;
    description?: string;
    tags?: string[];
  },
) {
  return apiClient.patch<PostItem>(`/posts/${requirementId}`, payload);
}

export async function draftRequirementWithAi(payload: {
  idea: string;
}) {
  return apiClient.post<{ title: string; description: string }>("/ai/suggestion-draft", payload);
}

export async function findSimilarRequirements(payload: {
  title: string;
  description: string;
  limit?: number;
}) {
  return apiClient.post<SimilarRequirementsResponse>("/ai/similar-requirements", payload);
}

export async function voteRequirement(requirementId: string) {
  return apiClient.post<{ success: boolean; message: string }>(`/posts/${requirementId}/vote`);
}

export async function convertRequirementToTask(
  requirementId: string,
  payload: {
    title: string;
    description_markdown: string;
    assignee_user_id: string | null;
    labels: string[];
  },
) {
  return apiClient.post<{ task: { id: string; number: number; title: string; status: string } }>(
    `/posts/${requirementId}/convert-to-task`,
    {
      ...payload,
      status: "todo",
    },
  );
}

export async function fetchTags() {
  return apiClient.get<{ items: Array<{ id: string; name: string; slug: string; color: string }> }>("/tags");
}

export async function createTag(payload: { name: string; color: string }) {
  return apiClient.post<{ success: boolean; message: string }>("/tags", payload);
}

export async function markDuplicate(requirementId: string, originalPostId: string) {
  return apiClient.post<{ id: string }>(`/posts/${requirementId}/duplicate`, {
    original_post_id: originalPostId,
  });
}

export async function archiveRequirement(requirementId: string) {
  return apiClient.post<{ id: string }>(`/posts/${requirementId}/archive`);
}

export async function fetchCurrentUser() {
  const data = await apiClient.get<CurrentUserResponse>("/auth/me");
  if (data.user !== undefined) {
    return data.user;
  }
  if (data.id && data.name) {
    return { id: data.id, name: data.name };
  }
  return null;
}

export async function logoutCurrentUser() {
  return apiClient.post<{ success: boolean; message: string }>("/auth/logout");
}

export async function exchangeFeishuClientCode(code: string) {
  return apiClient.post<{ success: boolean; user?: CurrentUser }>("/auth/feishu/client/exchange", { code });
}

import { apiClient } from "../../api/client";
import type {
  CommentListResponse,
  CurrentUser,
  RequirementListResponse,
  RequirementStatus,
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
  comments_count: number;
  has_voted?: boolean;
  user: { name: string; id: string };
  tags: Array<{ slug: string; name: string; color: string }>;
  response?: { text: string } | null;
  duplicate_of?: { number: number; title: string } | null;
  created_at: string;
  updated_at: string;
};

type CurrentUserResponse = {
  user?: CurrentUser | null;
} & Partial<CurrentUser>;

type PostListResponse = {
  items: PostItem[];
};

type PostCommentItem = {
  id: string;
  post_id: string;
  author: { name: string };
  body: string;
  created_at: string;
};

type PostCommentListResponse = {
  items: PostCommentItem[];
};

const statusToPostStatus: Record<RequirementStatus, PostStatus> = {
  backlog: "open",
  approved: "planned",
  in_progress: "in_progress",
  done: "completed",
  rejected: "declined",
};

const postStatusToStatus: Record<PostStatus, RequirementStatus> = {
  open: "backlog",
  planned: "approved",
  in_progress: "in_progress",
  completed: "done",
  declined: "rejected",
  duplicate: "rejected",
};

const statusResponseText: Record<RequirementStatus, string> = {
  backlog: "这个建议正在收集投票和讨论。",
  approved: "这个建议已有足够反馈，已进入规划。",
  in_progress: "团队正在处理这个建议。",
  done: "这个建议已经上线或解决。",
  rejected: "这个建议暂不符合当前产品方向。",
};

export async function fetchRequirements() {
  const data = await apiClient.get<PostListResponse>("/posts");
  return {
    items: data.items.map((item) => ({
      id: item.id,
      req_id: `POST-${item.number}`,
      title: item.title,
      description: item.description,
      status: postStatusToStatus[item.status],
      vote_count: item.votes_count,
      has_voted: Boolean(item.has_voted),
      creator_name: item.user.name,
      creator_open_id: item.user.id,
      created_at: item.created_at,
      updated_at: item.updated_at,
    })),
  } satisfies RequirementListResponse;
}

export async function createRequirement(payload: {
  title: string;
  description: string;
}) {
  return apiClient.post<{ id: string }>("/posts", {
    title: payload.title,
    description: payload.description,
    tags: [],
  });
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

export async function updateRequirementStatus(
  requirementId: string,
  payload: { status: RequirementStatus },
) {
  return apiClient.post<{ id: string }>(
    `/posts/${requirementId}/response`,
    {
      status: statusToPostStatus[payload.status],
      text: statusResponseText[payload.status],
    },
  );
}

export async function fetchComments(requirementId: string) {
  const data = await apiClient.get<PostCommentListResponse>(`/posts/${requirementId}/comments`);
  return {
    items: data.items.map((item) => ({
      id: item.id,
      requirement_id: item.post_id,
      author_name: item.author.name,
      body: item.body,
      created_at: item.created_at,
    })),
  } satisfies CommentListResponse;
}

export async function createComment(
  requirementId: string,
  payload: {
    body: string;
  },
) {
  return apiClient.post<{ success: boolean; message: string }>(
    `/posts/${requirementId}/comments`,
    {
      body: payload.body,
    },
  );
}

export async function fetchTags() {
  return apiClient.get<{ items: Array<{ id: string; name: string; slug: string; color: string }> }>("/tags");
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
  if (data.id && data.name && data.role) {
    return { id: data.id, name: data.name, role: data.role };
  }
  return null;
}

export async function logoutCurrentUser() {
  return apiClient.post<{ success: boolean; message: string }>("/auth/logout");
}

export async function exchangeFeishuClientCode(code: string) {
  return apiClient.post<{ success: boolean; user?: CurrentUser }>("/auth/feishu/client/exchange", { code });
}

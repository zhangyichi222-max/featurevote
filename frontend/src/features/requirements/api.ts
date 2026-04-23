import { apiClient } from "../../api/client";
import type { CommentListResponse, RequirementListResponse, RequirementStatus } from "../../types/requirement";

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
  user: { name: string; id: string };
  tags: Array<{ slug: string; name: string; color: string }>;
  response?: { text: string } | null;
  duplicate_of?: { number: number; title: string } | null;
  created_at: string;
  updated_at: string;
};

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
  backlog: "This suggestion is open for votes and discussion.",
  approved: "This suggestion has enough signal to move into planning.",
  in_progress: "The team is actively working on this suggestion.",
  done: "This suggestion has shipped or has been resolved.",
  rejected: "This suggestion is not planned for the current product direction.",
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
  creator_name: string;
  creator_open_id: string;
}) {
  return apiClient.post<{ id: string }>("/posts", {
    title: payload.title,
    description: payload.description,
    author_name: payload.creator_name,
    author_external_id: payload.creator_open_id,
    tags: [],
  });
}

export async function voteRequirement(
  requirementId: string,
  payload: {
    voter_name: string;
    voter_open_id: string;
  },
) {
  return apiClient.post<{ success: boolean; message: string }>(
    `/posts/${requirementId}/vote`,
    {
      voter_name: payload.voter_name,
      voter_external_id: payload.voter_open_id,
    },
  );
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
    author_name: string;
    body: string;
  },
) {
  return apiClient.post<{ success: boolean; message: string }>(
    `/posts/${requirementId}/comments`,
    {
      author_name: payload.author_name,
      author_external_id: payload.author_name.toLowerCase().replace(/\s+/g, "-") || "anonymous",
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

export async function moderatePost(requirementId: string, isApproved: boolean) {
  return apiClient.post<{ id: string }>(`/posts/${requirementId}/moderation`, {
    is_approved: isApproved,
  });
}

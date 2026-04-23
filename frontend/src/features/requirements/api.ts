import { apiClient } from "../../api/client";
import type { CommentListResponse, RequirementListResponse, RequirementStatus } from "../../types/requirement";

export async function fetchRequirements() {
  return apiClient.get<RequirementListResponse>("/requirements");
}

export async function createRequirement(payload: {
  title: string;
  description: string;
  creator_name: string;
  creator_open_id: string;
}) {
  return apiClient.post<{ success: boolean; message: string }>("/requirements", payload);
}

export async function voteRequirement(
  requirementId: string,
  payload: {
    voter_name: string;
    voter_open_id: string;
  },
) {
  return apiClient.post<{ success: boolean; message: string }>(
    `/requirements/${requirementId}/vote`,
    payload,
  );
}

export async function updateRequirementStatus(
  requirementId: string,
  payload: { status: RequirementStatus },
) {
  return apiClient.post<{ success: boolean; message: string }>(
    `/requirements/${requirementId}/status`,
    payload,
  );
}

export async function fetchComments(requirementId: string) {
  return apiClient.get<CommentListResponse>(`/requirements/${requirementId}/comments`);
}

export async function createComment(
  requirementId: string,
  payload: {
    author_name: string;
    body: string;
  },
) {
  return apiClient.post<{ success: boolean; message: string }>(
    `/requirements/${requirementId}/comments`,
    payload,
  );
}

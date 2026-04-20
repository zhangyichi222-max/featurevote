import { apiClient } from "../../api/client";
import type { RequirementListResponse, RequirementStatus } from "../../types/requirement";

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

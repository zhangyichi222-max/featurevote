import { apiClient } from "../../api/client";

export interface AttachmentUploadResponse {
  url: string;
  object_name: string;
  filename: string;
  content_type: string;
  size: number;
  is_image: boolean;
}

export function uploadAttachment(file: File) {
  return apiClient.upload<AttachmentUploadResponse>("/attachments", file);
}

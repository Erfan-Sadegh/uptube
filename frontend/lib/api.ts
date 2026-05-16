export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type SubtitleSegment = {
  id: string;
  index: number;
  startMs: number;
  endMs: number;
  text: string;
  editedText: string | null;
};

export type Job = {
  id: string;
  aparatUrl: string;
  status: string;
  language: string;
  ownershipConfirmed: boolean;
  title: string | null;
  description: string | null;
  youtubeVideoUrl: string | null;
  errorCode: string | null;
  errorMessage: string | null;
  retryable: boolean;
  subtitles: SubtitleSegment[];
};

export type Me = {
  id: string;
  email: string;
  youtubeConnected: boolean;
  channelTitle: string | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {})
    }
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  me: () => request<Me>("/api/me"),
  startGoogle: () => request<{ url: string; state: string }>("/auth/google/start", { method: "POST" }),
  createJob: (aparatUrl: string, ownershipConfirmed: boolean, language = "fa") =>
    request<Job>("/api/jobs", {
      method: "POST",
      body: JSON.stringify({ aparatUrl, ownershipConfirmed, language })
    }),
  getJob: (jobId: string) => request<Job>(`/api/jobs/${jobId}`),
  updateMetadata: (jobId: string, title: string, description: string) =>
    request<Job>(`/api/jobs/${jobId}/metadata`, {
      method: "PUT",
      body: JSON.stringify({ title, description })
    }),
  updateSubtitles: (jobId: string, segments: Array<{ id: string; editedText: string | null }>) =>
    request<Job>(`/api/jobs/${jobId}/subtitles`, {
      method: "PUT",
      body: JSON.stringify({ segments })
    }),
  upload: (jobId: string) => request<Job>(`/api/jobs/${jobId}/upload`, { method: "POST" })
};

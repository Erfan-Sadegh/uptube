"use client";

import {
  Check,
  CheckCircle2,
  ExternalLink,
  Loader2,
  LogIn,
  Play,
  RefreshCcw,
  Save,
  ShieldCheck,
  UploadCloud,
  X
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { StatusPill } from "@/components/StatusPill";
import { SubtitleEditor } from "@/components/SubtitleEditor";
import { api, type Job, type Me, type SubtitleSegment } from "@/lib/api";

const activeStatuses = new Set([
  "queued",
  "validating",
  "downloading",
  "extracting_audio",
  "uploading_audio_to_metis",
  "transcribing",
  "uploading_video",
  "uploading_caption"
]);

const restorableStatuses = new Set([...activeStatuses, "awaiting_review"]);

const statusOrder = [
  "queued",
  "validating",
  "downloading",
  "extracting_audio",
  "uploading_audio_to_metis",
  "transcribing",
  "awaiting_review",
  "uploading_video",
  "uploading_caption",
  "completed"
];

const progressSteps = [
  ["queued", "Queue"],
  ["downloading", "Download"],
  ["transcribing", "Subtitle"],
  ["awaiting_review", "Review"],
  ["uploading_video", "Upload"],
  ["completed", "Done"]
] as const;

const statusCopy: Record<string, { title: string; detail: string }> = {
  queued: { title: "Queued", detail: "Your video is waiting for the worker." },
  validating: { title: "Checking Aparat", detail: "We are validating the link and reading video metadata." },
  downloading: { title: "Downloading video", detail: "The source file is being copied for processing." },
  extracting_audio: { title: "Extracting audio", detail: "FFmpeg is preparing a compact audio track." },
  uploading_audio_to_metis: { title: "Preparing transcription", detail: "The audio is being prepared for Metis Whisper." },
  transcribing: { title: "Generating subtitles", detail: "Metis Whisper is creating the subtitle text." },
  awaiting_review: { title: "Ready for review", detail: "Review the title, description, and subtitles before upload." },
  uploading_video: { title: "Uploading to YouTube", detail: "The private YouTube upload is running. Larger videos take longer." },
  uploading_caption: { title: "Attaching subtitles", detail: "The generated SRT file is being added to the YouTube video." },
  completed: { title: "Completed", detail: "The video and captions are available on YouTube." },
  failed: { title: "Failed", detail: "The job stopped before completion." }
};

function hasReachedStep(status: string | undefined, step: string) {
  if (!status || status === "failed") return false;
  const currentIndex = statusOrder.indexOf(status);
  const stepIndex = statusOrder.indexOf(step);
  return currentIndex >= 0 && stepIndex >= 0 && currentIndex >= stepIndex;
}

export default function Home() {
  const [me, setMe] = useState<Me | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [url, setUrl] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [segments, setSegments] = useState<SubtitleSegment[]>([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showJobError, setShowJobError] = useState(true);

  useEffect(() => {
    api.me().then(setMe).catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    const lastJobId = window.localStorage.getItem("uptube.lastJobId");
    if (!lastJobId) return;
    api
      .getJob(lastJobId)
      .then((loaded) => {
        if (restorableStatuses.has(loaded.status)) {
          applyJob(loaded);
        } else {
          window.localStorage.removeItem("uptube.lastJobId");
        }
      })
      .catch(() => window.localStorage.removeItem("uptube.lastJobId"));
  }, []);

  useEffect(() => {
    if (!job || !activeStatuses.has(job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        applyJob(await api.getJob(job.id));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not refresh job status.");
      }
    }, 4000);
    return () => window.clearInterval(timer);
  }, [job]);

  const isWorking = job ? activeStatuses.has(job.status) : false;
  const currentStatus = job ? statusCopy[job.status] || { title: job.status, detail: "" } : null;
  const canCreate = useMemo(
    () => url.trim().length > 8 && confirmed && !busy && !isWorking,
    [url, confirmed, busy, isWorking]
  );
  const canRetryUpload = job?.status === "failed" && job.errorCode === "upload_failed" && job.retryable;
  const canUpload = ((job?.status === "awaiting_review" || canRetryUpload) && me?.youtubeConnected && !busy) || false;
  const uploadBlockedReason =
    job?.status !== "awaiting_review" && !canRetryUpload
      ? "Upload becomes available after subtitle review."
      : !me?.youtubeConnected
        ? "Connect YouTube first."
        : null;

  function applyJob(next: Job) {
    setJob(next);
    setShowJobError(true);
    if (next.status === "completed" || next.status === "failed") {
      window.localStorage.removeItem("uptube.lastJobId");
    } else {
      window.localStorage.setItem("uptube.lastJobId", next.id);
    }
    setSegments(next.subtitles);
    setTitle(next.title || "");
    setDescription(next.description || "");
  }

  function clearCurrentJob() {
    setJob(null);
    setSegments([]);
    setTitle("");
    setDescription("");
    setError(null);
    window.localStorage.removeItem("uptube.lastJobId");
  }

  async function connectYoutube() {
    if (me?.youtubeConnected) return;
    setError(null);
    const response = await api.startGoogle();
    window.location.href = response.url;
  }

  async function createJob() {
    setBusy(true);
    setError(null);
    setShowJobError(false);
    try {
      applyJob(await api.createJob(url, confirmed));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start processing.");
    } finally {
      setBusy(false);
    }
  }

  async function saveReview() {
    if (!job || job.status !== "awaiting_review") return;
    setBusy(true);
    setError(null);
    try {
      const withMetadata = await api.updateMetadata(job.id, title || "Aparat video", description);
      const saved = await api.updateSubtitles(
        withMetadata.id,
        segments.map((segment) => ({ id: segment.id, editedText: segment.editedText ?? segment.text }))
      );
      applyJob(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save review changes.");
    } finally {
      setBusy(false);
    }
  }

  async function upload() {
    if (!job) return;
    setBusy(true);
    setError(null);
    try {
      if (job.status === "awaiting_review") {
        const withMetadata = await api.updateMetadata(job.id, title || "Aparat video", description);
        await api.updateSubtitles(
          withMetadata.id,
          segments.map((segment) => ({ id: segment.id, editedText: segment.editedText ?? segment.text }))
        );
      }
      const queued = await api.upload(job.id);
      applyJob(queued);
      window.setTimeout(async () => {
        try {
          applyJob(await api.getJob(job.id));
        } catch {
          // Regular polling will continue while the job is active.
        }
      }, 1000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not upload to YouTube.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f6f8f7] text-ink">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-5 py-6 md:py-8">
        <header className="flex flex-col gap-5 border-b border-[#dfe6e2] pb-6 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-sm font-semibold text-moss">Uptube</p>
            <h1 className="mt-2 max-w-3xl text-3xl font-semibold leading-tight md:text-4xl">
              Aparat to YouTube with editable subtitles
            </h1>
          </div>
          <button
            className="focus-ring inline-flex h-11 items-center justify-center gap-2 rounded-md border border-[#cdd7d2] bg-white px-4 text-sm font-semibold text-ink shadow-sm transition hover:border-[#b8c8c1] disabled:cursor-default disabled:border-emerald-200 disabled:bg-emerald-50 disabled:text-emerald-700"
            disabled={Boolean(me?.youtubeConnected)}
            onClick={connectYoutube}
          >
            {me?.youtubeConnected ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <LogIn className="h-4 w-4" />}
            {me?.youtubeConnected ? me.channelTitle || "YouTube connected" : "Connect YouTube"}
          </button>
        </header>

        <section className="rounded-md border border-[#dfe6e2] bg-white p-5 shadow-[0_12px_35px_rgba(31,41,51,0.06)]">
          <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-end">
            <div className="space-y-3">
              <label className="text-sm font-semibold text-ink" htmlFor="aparatUrl">
                Aparat video link
              </label>
              <input
                id="aparatUrl"
                className="focus-ring h-12 w-full rounded-md border border-[#cdd7d2] bg-[#fbfcfb] px-3 text-left text-sm"
                dir="ltr"
                placeholder="https://www.aparat.com/v/..."
                value={url}
                onChange={(event) => {
                  setUrl(event.target.value);
                  setError(null);
                }}
              />
              <label className="flex items-start gap-3 text-sm leading-7 text-slate-600">
                <input
                  type="checkbox"
                  className="mt-1 h-4 w-4 accent-moss"
                  checked={confirmed}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                I own this content or have permission to publish it on YouTube.
              </label>
            </div>
            <button
              className="focus-ring inline-flex h-12 items-center justify-center gap-2 rounded-md bg-moss px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#274d43] disabled:cursor-not-allowed disabled:bg-slate-300"
              disabled={!canCreate}
              onClick={createJob}
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              Start processing
            </button>
          </div>
        </section>

        <section className="rounded-md border border-[#dfe6e2] bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <h2 className="text-base font-semibold">Status</h2>
              {job ? <StatusPill status={job.status} /> : <span className="text-sm text-slate-400">No active job</span>}
            </div>
            <div className="flex items-center gap-3 text-sm text-slate-500">
              <span className="inline-flex items-center gap-1">
                <ShieldCheck className="h-4 w-4 text-moss" />
                YouTube output: Private
              </span>
              {job ? (
                <button className="focus-ring inline-flex items-center gap-1 rounded-md px-2 py-1 text-moss" onClick={clearCurrentJob}>
                  <X className="h-4 w-4" />
                  Clear
                </button>
              ) : null}
            </div>
          </div>

          <div className="mt-4 grid grid-cols-6 gap-2">
            {progressSteps.map(([key, label]) => {
              const active = job?.status === key;
              const reached = hasReachedStep(job?.status, key);
              return (
                <div key={key} className="space-y-2">
                  <div
                    className={[
                      "h-2 rounded-full border border-[#dfe6e2] transition-colors",
                      active || reached ? "bg-moss" : "bg-[#eef3f0]"
                    ].join(" ")}
                    title={label}
                  />
                  <p className="truncate text-xs text-slate-500">{label}</p>
                </div>
              );
            })}
          </div>

          {currentStatus ? (
            <div
              className={[
                "mt-4 flex items-start gap-3 rounded-md border p-3 text-sm",
                job?.status === "completed"
                  ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                  : job?.status === "failed"
                    ? "border-red-200 bg-red-50 text-red-700"
                    : "border-[#d7e6df] bg-[#f3f8f5] text-slate-700"
              ].join(" ")}
            >
              {isWorking ? <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-moss" /> : <Check className="mt-0.5 h-4 w-4 shrink-0 text-moss" />}
              <div>
                <p className="font-semibold">{currentStatus.title}</p>
                <p className="mt-1 leading-6">{currentStatus.detail}</p>
              </div>
            </div>
          ) : null}

          {error ? (
            <div className="mt-4 flex items-center justify-between gap-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              <span>{error}</span>
              <button className="font-semibold" onClick={() => setError(null)}>Dismiss</button>
            </div>
          ) : null}
          {job?.status === "failed" && showJobError ? (
            <div className="mt-4 flex items-center justify-between gap-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              <span>{job.errorMessage}</span>
              <button className="font-semibold" onClick={() => setShowJobError(false)}>Dismiss</button>
            </div>
          ) : null}
          {job?.youtubeVideoUrl ? (
            <a
              className="focus-ring mt-4 inline-flex h-11 items-center justify-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-4 text-sm font-semibold text-emerald-700"
              href={job.youtubeVideoUrl}
              target="_blank"
            >
              <ExternalLink className="h-4 w-4" />
              Open YouTube video
            </a>
          ) : null}
        </section>

        <section className="grid gap-6 lg:grid-cols-[340px_1fr]">
          <div className="rounded-md border border-[#dfe6e2] bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-base font-semibold">Publishing details</h2>
            <div className="space-y-3">
              <input
                className="focus-ring h-11 w-full rounded-md border border-[#cdd7d2] bg-[#fbfcfb] px-3 text-sm disabled:text-slate-400"
                placeholder="YouTube title"
                value={title}
                disabled={job?.status !== "awaiting_review"}
                onChange={(event) => setTitle(event.target.value)}
              />
              <textarea
                className="focus-ring min-h-32 w-full resize-y rounded-md border border-[#cdd7d2] bg-[#fbfcfb] p-3 text-sm leading-7 disabled:text-slate-400"
                placeholder="YouTube description"
                value={description}
                disabled={job?.status !== "awaiting_review"}
                onChange={(event) => setDescription(event.target.value)}
              />
              <button
                className="focus-ring inline-flex h-11 w-full items-center justify-center gap-2 rounded-md border border-[#cdd7d2] bg-white text-sm font-semibold transition hover:border-[#b8c8c1] disabled:cursor-not-allowed disabled:text-slate-400"
                disabled={job?.status !== "awaiting_review" || busy}
                onClick={saveReview}
              >
                <Save className="h-4 w-4" />
                Save changes
              </button>
              <button
                className="focus-ring inline-flex h-11 w-full items-center justify-center gap-2 rounded-md bg-ink text-sm font-semibold text-white transition hover:bg-[#111827] disabled:cursor-not-allowed disabled:bg-slate-300"
                disabled={!canUpload}
                onClick={upload}
                title={uploadBlockedReason || undefined}
              >
                {busy || job?.status === "uploading_video" || job?.status === "uploading_caption" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : canRetryUpload ? (
                  <RefreshCcw className="h-4 w-4" />
                ) : (
                  <UploadCloud className="h-4 w-4" />
                )}
                {canRetryUpload ? "Retry YouTube upload" : "Upload to YouTube"}
              </button>
              {uploadBlockedReason ? <p className="text-xs leading-6 text-slate-500">{uploadBlockedReason}</p> : null}
            </div>
          </div>

          <div className="rounded-md border border-[#dfe6e2] bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-base font-semibold">Subtitles</h2>
              {job?.status === "awaiting_review" ? (
                <span className="inline-flex items-center gap-2 text-sm text-emerald-700">
                  <CheckCircle2 className="h-4 w-4" />
                  Ready for review
                </span>
              ) : (
                <span className="text-sm text-slate-400">Generated subtitles will appear here</span>
              )}
            </div>
            <SubtitleEditor segments={segments} onChange={setSegments} />
          </div>
        </section>
      </div>
    </main>
  );
}

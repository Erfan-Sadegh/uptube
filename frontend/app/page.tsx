"use client";

import {
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock3,
  ExternalLink,
  Flag,
  History,
  Languages,
  Loader2,
  Menu,
  Pencil,
  RefreshCcw,
  Subtitles,
  UploadCloud,
  X,
  Youtube
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { PointerEvent as ReactPointerEvent, ReactNode } from "react";

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
const MIYANDAR_CREDIT = "Synced with miyandar \u2665";
const MIYANDAR_CREDIT_MARKERS = ["made with miyandar", "synced with miyandar", "uploaded with miyandar"];

const statusCopy: Record<string, { title: string; detail: string }> = {
  queued: { title: "Added to Queue", detail: "Your sync job is waiting for the worker." },
  validating: { title: "Checking Aparat", detail: "We are validating the link and reading metadata." },
  downloading: { title: "Downloading Assets", detail: "The source video is being copied securely." },
  extracting_audio: { title: "Preparing Audio", detail: "FFmpeg is extracting a compact audio track." },
  uploading_audio_to_metis: { title: "Preparing STT", detail: "Audio chunks are being prepared for Metis." },
  transcribing: { title: "Generating Subtitles", detail: "Metis Whisper is creating timestamped subtitle text." },
  awaiting_review: { title: "Ready to Review", detail: "Review details, edit subtitles, then publish." },
  uploading_video: { title: "Publishing to YouTube", detail: "The private YouTube upload is running." },
  uploading_caption: { title: "Attaching Captions", detail: "The generated subtitle file is being attached." },
  completed: { title: "Published", detail: "Your video is ready on YouTube." },
  failed: { title: "Needs Attention", detail: "The job stopped before completion." },
  cancelled: { title: "Cancelled", detail: "This job was cancelled." }
};

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function stageProgress(job: Job | null, group: string) {
  if (!job) return { state: "pending", progress: 0, label: "Pending" };
  const status = job.status;
  if (status === "failed") return { state: "failed", progress: 0, label: "Stopped" };
  if (status === "cancelled") return { state: "failed", progress: 0, label: "Cancelled" };
  if (group === "queue") {
    return status === "queued"
      ? { state: "active", progress: 45, label: "Queued" }
      : { state: "done", progress: 100, label: "Completed" };
  }
  if (group === "download") {
    if (["validating", "downloading", "extracting_audio"].includes(status)) {
      return { state: "active", progress: clamp(job.progressPercent, 5, 65), label: `${job.progressPercent}%` };
    }
    if (job.progressPercent >= 28 || ["awaiting_review", "uploading_video", "uploading_caption", "completed"].includes(status)) {
      return { state: "done", progress: 100, label: "Completed" };
    }
  }
  if (group === "subtitle") {
    if (!job.subtitlesEnabled) return { state: "done", progress: 100, label: "Off" };
    if (["uploading_audio_to_metis", "transcribing"].includes(status)) {
      return { state: "active", progress: clamp(job.progressPercent - 35, 10, 95), label: `${job.progressPercent}%` };
    }
    if (["awaiting_review", "uploading_video", "uploading_caption", "completed"].includes(status)) {
      return { state: "done", progress: 100, label: "Completed" };
    }
  }
  if (group === "publish") {
    if (["uploading_video", "uploading_caption"].includes(status)) {
      return { state: "active", progress: clamp(job.progressPercent - 80, 10, 98), label: `${job.progressPercent}%` };
    }
    if (status === "completed") return { state: "done", progress: 100, label: "Completed" };
  }
  return { state: "pending", progress: 0, label: "Pending" };
}

function StageRow({
  icon,
  title,
  state,
  progress,
  label
}: {
  icon: ReactNode;
  title: string;
  state: string;
  progress: number;
  label: string;
}) {
  const active = state === "active";
  const done = state === "done";
  return (
    <div className={["grid grid-cols-[48px_1fr] gap-4 transition-opacity", state === "pending" ? "opacity-45" : "opacity-100"].join(" ")}>
      <div
        className={[
          "flex h-11 w-11 items-center justify-center rounded-full border transition-all",
          done
            ? "border-[#d9a39a] bg-[#fae4df] text-[#6f4a44]"
            : active
              ? "border-[#d98f87] bg-[#fff7f5] text-[#a95d55] shadow-[0_0_0_4px_rgba(217,143,135,0.12)]"
              : "border-[#d9d1cc] bg-[#f8f5f1] text-[#9a8d86]"
        ].join(" ")}
      >
        {done ? <Check className="h-5 w-5" /> : icon}
      </div>
      <div className="min-w-0 pt-1">
        <div className="flex items-center justify-between gap-3">
          <p className="truncate text-base font-semibold text-[#3b3431]">{title}</p>
          <p className={["text-sm font-semibold", active ? "text-[#a95d55]" : done ? "text-[#7b625d]" : "text-[#9a8d86]"].join(" ")}>
            {label}
          </p>
        </div>
        <div className="mt-3 h-1.5 rounded-full bg-[#e6ded8]">
          <div
            className={[
              "h-1.5 rounded-full transition-all duration-700",
              done ? "bg-[#d9a39a]" : active ? "bg-[#d98f87]" : "bg-transparent"
            ].join(" ")}
            style={{ width: `${clamp(progress, 0, 100)}%` }}
          />
        </div>
      </div>
    </div>
  );
}

function timeLabel(ms: number) {
  const seconds = Math.floor(ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function withMiyandarCredit(value: string) {
  const lines = value.trimEnd().split("\n");
  while (lines.length > 0 && !lines[lines.length - 1].trim()) lines.pop();
  if (lines.length > 0 && isMiyandarCredit(lines[lines.length - 1])) {
    lines[lines.length - 1] = MIYANDAR_CREDIT;
    return lines.join("\n");
  }
  const cleaned = lines.join("\n");
  return cleaned ? `${cleaned}\n\n${MIYANDAR_CREDIT}` : MIYANDAR_CREDIT;
}

function isMiyandarCredit(line: string) {
  const lowered = line.trim().toLowerCase();
  return MIYANDAR_CREDIT_MARKERS.some((marker) => lowered.includes(marker));
}

export default function Home() {
  const [me, setMe] = useState<Me | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [url, setUrl] = useState("");
  const [subtitlesEnabled, setSubtitlesEnabled] = useState(true);
  const [language, setLanguage] = useState<"fa" | "en">("fa");
  const [segments, setSegments] = useState<SubtitleSegment[]>([]);
  const [editingSegmentId, setEditingSegmentId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [sheetHeight, setSheetHeight] = useState(420);
  const [maxSheetHeight, setMaxSheetHeight] = useState(640);
  const [drag, setDrag] = useState<{ startY: number; startHeight: number } | null>(null);
  const [reviewOpen, setReviewOpen] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .me()
      .then((currentUser) => {
        setMe(currentUser);
        return refreshJobs();
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    const setResponsiveHeight = () => {
      const nextMax = Math.min(Math.round(window.innerHeight * 0.72), 720);
      setMaxSheetHeight(nextMax);
      setSheetHeight((current) => clamp(current, 112, nextMax));
    };
    setResponsiveHeight();
    window.addEventListener("resize", setResponsiveHeight);
    return () => window.removeEventListener("resize", setResponsiveHeight);
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
    }, 3000);
    return () => window.clearInterval(timer);
  }, [job]);

  useEffect(() => {
    if (!job) return;
    if (job.status === "awaiting_review") setSheetHeight(maxSheetHeight);
    else if (job.status === "completed") setSheetHeight(Math.min(maxSheetHeight, 460));
    else if (job.status === "failed" || job.status === "cancelled") setSheetHeight(Math.min(maxSheetHeight, 380));
    else setSheetHeight(Math.min(maxSheetHeight, 500));
  }, [job?.status, maxSheetHeight]);

  const currentStatus = job ? statusCopy[job.status] || { title: job.status, detail: "" } : null;
  const isWorking = job ? activeStatuses.has(job.status) : false;
  const canRetryUpload = Boolean(job?.status === "failed" && job.errorCode === "upload_failed" && job.retryable && me?.youtubeConnected);
  const canRetryProcessing = Boolean(job?.status === "failed" && job.errorCode === "processing_failed" && job.retryable);
  const canCancel = Boolean(job && (activeStatuses.has(job.status) || job.status === "awaiting_review"));
  const canStart = useMemo(
    () => url.trim().length > 8 && Boolean(me?.youtubeConnected) && !busy && !isWorking,
    [url, me?.youtubeConnected, busy, isWorking]
  );
  const primaryDisabled = Boolean((me?.youtubeConnected && !canStart) || busy || isWorking);
  const canUpload = Boolean(job?.status === "awaiting_review" && me?.youtubeConnected && !busy);
  const showSheetFooter = Boolean(job && (job.status === "awaiting_review" || canRetryProcessing || canRetryUpload || job.status === "failed"));

  function applyJob(next: Job) {
    setJob(next);
    setJobs((current) => [next, ...current.filter((item) => item.id !== next.id)].slice(0, 12));
    setSegments(next.subtitles);
    setTitle(next.title || "");
    setDescription(next.status === "awaiting_review" ? withMiyandarCredit(next.description || "") : next.description || "");
    if (next.status === "completed" || next.status === "failed" || next.status === "cancelled") {
      window.localStorage.removeItem("uptube.lastJobId");
    } else {
      window.localStorage.setItem("uptube.lastJobId", next.id);
    }
  }

  async function refreshJobs() {
    const loaded = await api.listJobs();
    setJobs(loaded);
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
    try {
      const created = await api.createJob(url, true, language, subtitlesEnabled);
      applyJob(created);
      await refreshJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start sync.");
    } finally {
      setBusy(false);
    }
  }

  async function saveReview() {
    if (!job || job.status !== "awaiting_review") return job;
    const reviewedDescription = withMiyandarCredit(description);
    setDescription(reviewedDescription);
    const withMetadata = await api.updateMetadata(job.id, title || "Aparat video", reviewedDescription);
    if (!job.subtitlesEnabled) {
      applyJob(withMetadata);
      return withMetadata;
    }
    const saved = await api.updateSubtitles(
      withMetadata.id,
      segments.map((segment) => ({ id: segment.id, editedText: segment.editedText ?? segment.text }))
    );
    applyJob(saved);
    return saved;
  }

  async function publish() {
    if (!job) return;
    setBusy(true);
    setError(null);
    try {
      const reviewed = job.status === "awaiting_review" ? await saveReview() : job;
      if (!reviewed) return;
      const queued = await api.upload(reviewed.id);
      applyJob(queued);
      await refreshJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not publish to YouTube.");
    } finally {
      setBusy(false);
    }
  }

  async function retryProcessing() {
    if (!job) return;
    setBusy(true);
    setError(null);
    try {
      applyJob(await api.retryJob(job.id));
      await refreshJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not retry this sync.");
    } finally {
      setBusy(false);
    }
  }

  async function cancelAndCloseJob() {
    await cancelCurrentJob(true);
  }

  async function cancelCurrentJob(closeAfterCancel: boolean) {
    if (!job) return;
    setBusy(true);
    setError(null);
    try {
      const cancelled = await api.cancelJob(job.id);
      if (!closeAfterCancel) applyJob(cancelled);
      await refreshJobs();
      if (closeAfterCancel) closeSheet();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not cancel this job.");
    } finally {
      setBusy(false);
    }
  }

  async function reportJob() {
    if (!job) return;
    setError(null);
    try {
      await api.reportJob(job.id, "technical_issue", job.progressMessage || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit report.");
    }
  }

  function closeSheet() {
    setJob(null);
    setSegments([]);
    setEditingSegmentId(null);
    window.localStorage.removeItem("uptube.lastJobId");
  }

  function onDragStart(event: ReactPointerEvent<HTMLDivElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrag({ startY: event.clientY, startHeight: sheetHeight });
  }

  function onDragMove(event: ReactPointerEvent<HTMLDivElement>) {
    if (!drag) return;
    const next = drag.startHeight + (drag.startY - event.clientY);
    setSheetHeight(clamp(next, 112, maxSheetHeight));
  }

  function onDragEnd() {
    setDrag(null);
  }

  return (
    <main className="min-h-screen overflow-hidden bg-[#f7f3ee] text-[#3b3431]">
      <div className={["min-h-screen transition duration-300", job ? "blur-[2px]" : ""].join(" ")}>
        <div className="mx-auto flex min-h-screen max-w-3xl flex-col px-6">
          <header className="flex h-20 items-center justify-between border-b border-[#ded4cd]">
            <div className="h-10 w-10" />
            <div className="text-2xl font-black tracking-[0.08em] text-[#d98f87] drop-shadow-[0_2px_0_rgba(91,65,60,0.16)]">
              UPTUBE
            </div>
            <button className="focus-ring relative inline-flex h-10 w-10 items-center justify-center rounded-md text-[#7b625d]" onClick={() => setMenuOpen((value) => !value)}>
              <Menu className="h-6 w-6" />
            </button>
          </header>

          {menuOpen ? (
            <div className="absolute right-6 top-20 z-20 w-[min(340px,calc(100vw-48px))] rounded-md border border-[#ded4cd] bg-white/95 p-3 shadow-[0_18px_60px_rgba(70,50,45,0.13)] backdrop-blur">
              <div className="mb-3 flex items-center justify-between">
                <p className="inline-flex items-center gap-2 text-sm font-bold">
                  <History className="h-4 w-4 text-[#a95d55]" />
                  Recent jobs
                </p>
                <button className="text-xs font-bold text-[#7b625d]" onClick={refreshJobs}>
                  Refresh
                </button>
              </div>
              <div className="max-h-80 space-y-2 overflow-y-auto">
                {jobs.length === 0 ? <p className="p-2 text-sm text-slate-500">No recent jobs yet.</p> : null}
                {jobs.map((item) => (
                  <button
                    key={item.id}
                    className="focus-ring w-full rounded-md border border-[#ded4cd] bg-[#faf8f5] p-3 text-left transition hover:border-[#d9a39a]"
                    onClick={async () => {
                      setMenuOpen(false);
                      applyJob(await api.getJob(item.id));
                    }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-bold">{item.title || item.aparatUrl}</span>
                      <span className="text-xs text-slate-500">{item.progressPercent}%</span>
                    </div>
                    <div className="mt-2 h-1.5 rounded-full bg-[#e6ded8]">
                      <div className="h-1.5 rounded-full bg-[#d98f87]" style={{ width: `${item.progressPercent}%` }} />
                    </div>
                    <p className="mt-2 truncate text-xs text-slate-500">{item.progressMessage || item.status}</p>
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          <section className="flex flex-1 flex-col justify-center py-10">
            <h1 className="text-center text-4xl font-black uppercase leading-tight tracking-normal text-[#3b3431] drop-shadow-[0_4px_0_rgba(217,163,154,0.58)] md:text-6xl">
              Sync Your
              <br />
              Content
            </h1>
            <p className="mx-auto mt-7 max-w-xl text-center text-lg font-semibold leading-8 text-[#7b625d]">
              Bridge Aparat to YouTube with subtitles.
            </p>

            <div className="mx-auto mt-12 w-full max-w-[560px] space-y-7">
              <div className="flex items-center justify-between gap-4 rounded-md border border-[#ded4cd] bg-white/78 p-4 shadow-[0_10px_26px_rgba(70,50,45,0.06)]">
                <div className="flex items-center gap-3">
                  <div className={["flex h-11 w-11 items-center justify-center rounded-full", me?.youtubeConnected ? "bg-[#e5f3ec]" : "bg-[#efe9e4]"].join(" ")}>
                    {me?.youtubeConnected ? (
                      <CheckCircle2 className="h-5 w-5 text-[#27734f]" />
                    ) : (
                      <Youtube className="h-5 w-5 text-[#7b625d]" />
                    )}
                  </div>
                  <div>
                    <p className="text-sm font-black text-[#3b3431]">YouTube</p>
                    <p className={["mt-0.5 text-xs font-black uppercase tracking-[0.16em]", me?.youtubeConnected ? "text-[#27734f]" : "text-[#8d817b]"].join(" ")}>
                      {me?.youtubeConnected ? "Connected" : "Disconnected"}
                    </p>
                  </div>
                </div>
                {!me?.youtubeConnected ? (
                  <button
                    className="focus-ring h-10 rounded-full bg-[#d98f87] px-5 text-xs font-black uppercase tracking-[0.08em] text-white shadow-[0_8px_18px_rgba(169,93,85,0.18)]"
                    onClick={connectYoutube}
                  >
                    Connect
                  </button>
                ) : null}
              </div>

              <div>
                <label className="text-sm font-black uppercase tracking-[0.18em] text-[#7b625d]" htmlFor="aparatUrl">
                  Aparat video URL
                </label>
                <input
                  id="aparatUrl"
                  className="focus-ring mt-4 h-16 w-full rounded-md border border-[#d4c9c2] bg-white px-5 text-left text-lg font-semibold text-[#3b3431] placeholder:text-[#aa9d97]"
                  dir="ltr"
                  placeholder="https://www.aparat.com/v/..."
                  value={url}
                  onChange={(event) => {
                    setUrl(event.target.value);
                    setError(null);
                  }}
                />
              </div>

              <div className="border-t border-[#ded4cd] pt-7">
                <div className="flex items-center justify-between gap-4">
                  <div className="inline-flex items-center gap-3 text-lg font-black">
                    <Subtitles className="h-5 w-5 text-[#7b625d]" />
                    Subtitle Syncing
                  </div>
                  <button
                    className={[
                      "relative h-9 w-16 rounded-full p-1 transition",
                      subtitlesEnabled ? "bg-[#d9a39a]" : "bg-[#d6d0cb]"
                    ].join(" ")}
                    onClick={() => setSubtitlesEnabled((value) => !value)}
                    aria-pressed={subtitlesEnabled}
                  >
                    <span
                      className={[
                        "block h-7 w-7 rounded-full bg-white shadow transition-transform",
                        subtitlesEnabled ? "translate-x-7" : "translate-x-0"
                      ].join(" ")}
                    />
                  </button>
                </div>

                <div className="mt-6 flex items-center justify-between gap-4">
                  <div className="inline-flex items-center gap-3 text-lg font-black">
                    <Languages className="h-5 w-5 text-[#7b625d]" />
                    Language
                  </div>
                  <div className={["grid grid-cols-2 rounded-md border border-[#d4c9c2] bg-white p-1", subtitlesEnabled ? "" : "opacity-45"].join(" ")}>
                    {(["fa", "en"] as const).map((item) => (
                      <button
                        key={item}
                        className={[
                          "h-9 rounded px-4 text-sm font-black transition",
                          language === item ? "bg-[#f2d2cc] text-[#6f4a44]" : "text-[#7b625d]"
                        ].join(" ")}
                        disabled={!subtitlesEnabled}
                        onClick={() => setLanguage(item)}
                      >
                        {item === "fa" ? "Persian" : "English"}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {error ? <p className="rounded-md border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-700">{error}</p> : null}

              <button
                className="focus-ring inline-flex h-16 w-full items-center justify-center gap-4 rounded-full bg-[#d98f87] text-sm font-black uppercase tracking-[0.24em] text-white shadow-[0_18px_34px_rgba(169,93,85,0.20)] transition hover:bg-[#cf8178] disabled:cursor-not-allowed disabled:bg-[#d4d0cd] disabled:text-[#847b78] disabled:shadow-none"
                disabled={primaryDisabled}
                onClick={me?.youtubeConnected ? createJob : connectYoutube}
              >
                {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : null}
                {me?.youtubeConnected ? "Sync now" : "Connect YouTube"}
                <ArrowRight className="h-5 w-5" />
              </button>
              <p className="text-center text-xs font-semibold leading-6 text-[#7b625d]">
                By syncing, you confirm you own this content or have permission to publish it.
              </p>
            </div>
          </section>

          <footer className="flex h-24 flex-col items-center justify-center gap-4 border-t border-[#ded4cd] text-sm font-bold text-[#7b625d]">
            <div className="flex gap-8">
              <span>Guide</span>
              <span>Terms</span>
              <span>Privacy</span>
            </div>
            <p className="text-[#3b3431]">Uptube Engine (c) 2026</p>
          </footer>
        </div>
      </div>

      {job ? (
        <div className="fixed inset-x-0 bottom-0 z-40 mx-auto max-w-3xl px-0 md:px-4">
          <section
            className="relative overflow-hidden rounded-t-[32px] border border-[#ded4cd] bg-[#fbf8f4] text-[#3b3431] shadow-[0_-24px_80px_rgba(70,50,45,0.18)] transition-[height] duration-300"
            style={{ height: sheetHeight }}
          >
            <div
              className="flex cursor-grab touch-none justify-center pt-5 active:cursor-grabbing"
              onPointerDown={onDragStart}
              onPointerMove={onDragMove}
              onPointerUp={onDragEnd}
              onPointerCancel={onDragEnd}
            >
              <div className="h-1.5 w-20 rounded-full bg-[#cfc6c0]" />
            </div>

            <div className="flex h-[calc(100%-28px)] flex-col px-6 pb-0">
              <div className="mt-8 flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-3xl font-black text-[#3b3431]">{currentStatus?.title}</h2>
                  <p className="mt-3 text-lg font-semibold leading-7 text-[#7b625d]">
                    {job.progressMessage || currentStatus?.detail}
                  </p>
                </div>
                {canCancel ? (
                  <button
                    className="focus-ring inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-full border border-[#ded4cd] bg-white/75 px-3 text-xs font-black uppercase tracking-[0.08em] text-[#7b625d] disabled:opacity-45"
                    disabled={busy}
                    onClick={cancelAndCloseJob}
                  >
                    {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <X className="h-3.5 w-3.5" />}
                    Cancel
                  </button>
                ) : job.status === "completed" || job.status === "failed" || job.status === "cancelled" ? (
                  <button className="focus-ring rounded-md p-2 text-[#7b625d]" onClick={closeSheet}>
                    <X className="h-5 w-5" />
                  </button>
                ) : null}
              </div>

              <div className="mt-7 h-1.5 rounded-full bg-[#e6ded8]">
                <div
                  className="h-1.5 rounded-full bg-[#d98f87] transition-all duration-700"
                  style={{ width: `${clamp(job.progressPercent, 0, 100)}%` }}
                />
              </div>

              {job.status === "awaiting_review" ? (
                <button
                  className="focus-ring mt-5 inline-flex h-12 w-full shrink-0 items-center justify-center gap-3 rounded-full bg-[#d98f87] text-sm font-black uppercase tracking-[0.16em] text-white shadow-[0_12px_28px_rgba(169,93,85,0.18)] disabled:bg-[#d4d0cd] disabled:text-[#847b78] disabled:shadow-none"
                  disabled={!canUpload}
                  onClick={publish}
                >
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}
                  Publish to YouTube
                </button>
              ) : null}

              <div className={["mt-8 min-h-0 flex-1 overflow-y-auto pr-1", showSheetFooter ? "pb-28" : "pb-4"].join(" ")}>
                {job.status === "awaiting_review" ? (
                  <div className="space-y-4">
                    <button
                      className="flex w-full items-center justify-between rounded-md border border-[#ded4cd] bg-white p-4 text-left"
                      onClick={() => {
                        setReviewOpen((value) => !value);
                        setSheetHeight(reviewOpen ? 260 : maxSheetHeight);
                      }}
                    >
                      <div>
                        <p className="text-lg font-black">Review before publishing</p>
                        <p className="mt-1 text-sm font-semibold text-[#7b625d]">
                          {job.subtitlesEnabled ? `${segments.length} subtitle segments` : "Subtitles are off for this job"}
                        </p>
                      </div>
                      {reviewOpen ? <ChevronDown className="h-5 w-5" /> : <ChevronUp className="h-5 w-5" />}
                    </button>

                    {reviewOpen ? (
                      <div className="space-y-4">
                        <div className="grid gap-3">
                          <input
                            className="focus-ring h-12 rounded-md border border-[#d4c9c2] bg-white px-4 text-sm font-semibold text-[#3b3431] placeholder:text-[#aa9d97]"
                            placeholder="YouTube title"
                            value={title}
                            onChange={(event) => setTitle(event.target.value)}
                          />
                          <textarea
                            className="focus-ring min-h-24 resize-y rounded-md border border-[#d4c9c2] bg-white p-4 text-sm font-semibold leading-6 text-[#3b3431] placeholder:text-[#aa9d97]"
                            placeholder="YouTube description"
                            value={description}
                            onChange={(event) => setDescription(event.target.value)}
                          />
                        </div>

                        {job.subtitlesEnabled ? (
                          <div className="max-h-[26vh] space-y-3 overflow-y-auto rounded-md border border-[#ded4cd] bg-[#f7f3ee] p-3 md:max-h-[34vh]">
                            {segments.map((segment) => {
                              const editing = editingSegmentId === segment.id;
                              return (
                                <div key={segment.id} className="rounded-md border border-[#e1d7d0] bg-white p-3 text-[#3b3431] shadow-sm">
                                  <div className="mb-2 flex items-center justify-between gap-3">
                                    <span className="font-mono text-xs font-bold text-[#a95d55]">
                                      {timeLabel(segment.startMs)} - {timeLabel(segment.endMs)}
                                    </span>
                                    <button
                                      className="focus-ring rounded p-1 text-[#a95d55]"
                                      onClick={() => setEditingSegmentId(editing ? null : segment.id)}
                                    >
                                      {editing ? <CheckCircle2 className="h-4 w-4" /> : <Pencil className="h-4 w-4" />}
                                    </button>
                                  </div>
                                  {editing ? (
                                    <textarea
                                      className="focus-ring min-h-24 w-full resize-y rounded border border-[#ded4cd] bg-[#fbf8f4] p-3 text-sm leading-6 text-[#3b3431]"
                                      value={segment.editedText ?? segment.text}
                                      onChange={(event) =>
                                        setSegments((current) =>
                                          current.map((item) =>
                                            item.id === segment.id ? { ...item, editedText: event.target.value } : item
                                          )
                                        )
                                      }
                                    />
                                  ) : (
                                    <p className="line-clamp-3 text-sm font-semibold leading-6 text-[#3b3431]">
                                      {segment.editedText ?? segment.text}
                                    </p>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div className="space-y-8">
                    <StageRow icon={<Clock3 className="h-5 w-5" />} title="Added to Queue" {...stageProgress(job, "queue")} />
                    <StageRow icon={<ArrowRight className="h-5 w-5" />} title="Downloading Assets" {...stageProgress(job, "download")} />
                    <StageRow icon={<Subtitles className="h-5 w-5" />} title="Generating Subtitles" {...stageProgress(job, "subtitle")} />
                    <StageRow icon={<UploadCloud className="h-5 w-5" />} title="Publishing to YouTube" {...stageProgress(job, "publish")} />
                  </div>
                )}

                {error ? <p className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-700">{error}</p> : null}

                {job.status === "completed" && job.youtubeVideoUrl ? (
                  <a
                    className="focus-ring mt-6 inline-flex h-12 w-full items-center justify-center gap-3 rounded-full bg-[#d98f87] text-sm font-black uppercase tracking-[0.16em] text-white"
                    href={job.youtubeVideoUrl}
                    target="_blank"
                  >
                    Open on YouTube
                    <ExternalLink className="h-4 w-4" />
                  </a>
                ) : null}
              </div>

            </div>

            {showSheetFooter ? (
              <div className="absolute inset-x-0 bottom-0 z-20 flex items-center justify-center gap-4 border-t border-[#ded4cd] bg-[#fbf8f4]/95 px-6 pt-3 pb-[calc(14px+env(safe-area-inset-bottom))] backdrop-blur">
                {job.status === "awaiting_review" ? (
                  <button
                    className="focus-ring inline-flex h-12 w-full items-center justify-center gap-3 rounded-full bg-[#d98f87] text-sm font-black uppercase tracking-[0.16em] text-white shadow-[0_12px_28px_rgba(169,93,85,0.18)] disabled:bg-[#d4d0cd] disabled:text-[#847b78] disabled:shadow-none"
                    disabled={!canUpload}
                    onClick={publish}
                  >
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}
                    Publish to YouTube
                  </button>
                ) : canRetryProcessing ? (
                  <button
                    className="focus-ring inline-flex h-12 w-full items-center justify-center gap-3 rounded-full bg-[#d98f87] text-sm font-black uppercase tracking-[0.16em] text-white"
                    disabled={busy}
                    onClick={retryProcessing}
                  >
                    <RefreshCcw className="h-4 w-4" />
                    Retry Sync
                  </button>
                ) : canRetryUpload ? (
                  <button
                    className="focus-ring inline-flex h-12 w-full items-center justify-center gap-3 rounded-full bg-[#d98f87] text-sm font-black uppercase tracking-[0.16em] text-white"
                    disabled={busy}
                    onClick={publish}
                  >
                    <RefreshCcw className="h-4 w-4" />
                    Retry Upload
                  </button>
                ) : job.status === "failed" ? (
                  <button className="focus-ring inline-flex items-center gap-2 rounded-md px-4 py-3 text-sm font-black text-[#7b625d]" onClick={reportJob}>
                    <Flag className="h-4 w-4" />
                    Report issue
                  </button>
                ) : null}
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
    </main>
  );
}

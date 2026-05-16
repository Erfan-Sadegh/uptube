const labels: Record<string, string> = {
  queued: "Queued",
  validating: "Validating",
  downloading: "Downloading",
  extracting_audio: "Extracting audio",
  uploading_audio_to_metis: "Preparing STT",
  transcribing: "Transcribing",
  awaiting_review: "Review",
  uploading_video: "Uploading video",
  uploading_caption: "Attaching captions",
  completed: "Completed",
  failed: "Failed"
};

export function StatusPill({ status }: { status: string }) {
  const failed = status === "failed";
  const done = status === "completed";
  return (
    <span
      className={[
        "inline-flex h-8 items-center rounded-md border px-3 text-sm font-medium",
        failed
          ? "border-red-200 bg-red-50 text-red-700"
          : done
            ? "border-emerald-200 bg-emerald-50 text-emerald-700"
            : "border-[#cfdad5] bg-[#f7faf8] text-moss"
      ].join(" ")}
    >
      {labels[status] || status}
    </span>
  );
}

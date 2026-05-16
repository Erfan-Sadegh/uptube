"use client";

import type { SubtitleSegment } from "@/lib/api";

function timeLabel(ms: number) {
  const seconds = Math.floor(ms / 1000);
  const minute = Math.floor(seconds / 60);
  const second = seconds % 60;
  return `${minute}:${String(second).padStart(2, "0")}`;
}

export function SubtitleEditor({
  segments,
  onChange
}: {
  segments: SubtitleSegment[];
  onChange: (segments: SubtitleSegment[]) => void;
}) {
  return (
    <div className="max-h-[460px] overflow-y-auto rounded-md border border-[#dce4e0] bg-white">
      {segments.length === 0 ? (
        <div className="p-5 text-sm text-slate-500">Subtitles will appear here after transcription.</div>
      ) : (
        segments.map((segment) => (
          <div key={segment.id} className="grid gap-3 border-b border-[#edf1ef] p-4 last:border-b-0 md:grid-cols-[96px_1fr]">
            <div className="text-xs font-medium text-slate-500">
              {timeLabel(segment.startMs)} - {timeLabel(segment.endMs)}
            </div>
            <textarea
              className="focus-ring min-h-20 w-full resize-y rounded-md border border-[#dce4e0] bg-[#fbfcfb] p-3 text-sm leading-7"
              value={segment.editedText ?? segment.text}
              onChange={(event) =>
                onChange(
                  segments.map((item) =>
                    item.id === segment.id ? { ...item, editedText: event.target.value } : item
                  )
                )
              }
            />
          </div>
        ))
      )}
    </div>
  );
}

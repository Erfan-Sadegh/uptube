# Uptube Project Context

## Product
- MVP connects Aparat to YouTube for creators.
- Flow: paste Aparat link, connect YouTube, optionally generate subtitles, review/edit, upload private YouTube video, optionally attach captions, show final link.
- Supported subtitle languages in MVP: Persian (`fa`) and English (`en`).

## Locked Decisions
- STT provider: prefer AvalAI when `AVALAI_API_KEY` is configured; otherwise fall back to Metis Generations.
- AvalAI STT model default: `whisper-1` with `response_format=verbose_json` and `timestamp_granularities[]=word`.
- Metis result retrieval: polling every 5 seconds minimum. Webhook is later.
- Subtitle output: SRT only for MVP. No word-level timestamps or timeline editor.
- Metis currently fails completed jobs when `response_format=srt` is sent; use chunked text transcription and render SRT locally until Metis fixes that runtime bug.
- Metis also currently fails `response_format=verbose_json` in beta with a Java enum cast error; do not use it in production yet.
- AvalAI `response_format=srt` currently returned JSON/text in testing, so use word timestamps and render SRT locally.
- AvalAI requires system/proxy networking (`trust_env=True`); Metis requires direct networking (`trust_env=False`).
- YouTube privacy: always `private` in MVP.
- Aparat intake: API-first direct MP4 discovery with `yt-dlp` fallback, because no stable official download contract is assumed.
- Ownership gate: user must confirm they own or are allowed to republish the source video.
- Beta limits: max 30 minutes and max 500 MB by default.
- Per-user beta limits: daily job cap and active job cap are enforced from config.
- Progress is persisted on each job as `progress_percent` and `progress_message`.
- Subtitle generation is controlled per job by `subtitles_enabled`.
- Default YouTube descriptions keep the base upload text and append `Synced with miyandar ♥`.
- Do not send `prompt` to Metis `whisper-1`; beta testing showed the wrapper can echo prompt instructions into subtitle text.
- Default STT chunk size is 60 seconds for better context while keeping retries bounded.
- STT text is cleaned conservatively before SRT rendering to remove obvious repeated-word/letter noise or echoed instructions without rewriting meaning.
- Long chunk text is split into shorter local SRT rows; timings are approximate until a reliable timestamp response is used.
- AvalAI word timestamps are grouped into readable local SRT rows; this is the preferred subtitle path while it remains reliable.

## Security Rules
- Never commit real API keys, OAuth secrets, refresh tokens, or signed media URLs.
- The Metis key is only read from `METIS_API_KEY`.
- Google refresh tokens are encrypted before storage.
- Do not log Authorization headers or secret env values.
- `PROJECT_CONTEXT.md` must remain below 200 lines and must not contain secrets.

## Main Services
- Frontend: Next.js, TypeScript, Tailwind.
- API: FastAPI, Pydantic, SQLAlchemy.
- Worker: Redis/RQ-style async worker in Python.
- Storage: local/S3-compatible temporary artifacts plus Metis Storage for public audio URLs.
- Local mode falls back to FastAPI background tasks if Redis workers are not available.

## Job States
- `queued`
- `validating`
- `downloading`
- `extracting_audio`
- `uploading_audio_to_metis`
- `transcribing`
- `awaiting_review`
- `uploading_video`
- `uploading_caption`
- `completed`
- `failed`
- `cancelled`

## External Contracts
- Metis create: `POST https://api.metisai.ir/api/v2/generate`
- Metis poll: `GET https://api.metisai.ir/api/v2/generate/{generation_id}`
- Metis target STT args: `file`, `language`, `response_format=srt`, `temperature=0`; current implementation uses chunked text output and local SRT rendering while Metis SRT output fails.
- AvalAI transcribe: `POST https://api.avalai.ir/v1/audio/transcriptions` as multipart file upload.
- YouTube scopes: `youtube.upload` and `youtube.force-ssl`.
- Each completed job should budget at least 500 YouTube quota units.

## Implementation Notes
- Use adapters for Aparat, transcription, artifact storage, and YouTube.
- State changes must create job events.
- User can edit subtitle text only; segment timing stays unchanged.
- Upload starts only after `awaiting_review`.
- Upload UI must keep showing active progress while `uploading_video` or `uploading_caption`.
- If subtitles are disabled, audio extraction, Metis transcription, and caption upload are skipped.
- STT chunks can run in limited parallelism (`METIS_PARALLEL_CHUNKS`) for speed; chunk size is configurable via `AUDIO_CHUNK_SECONDS`.
- Cleanup deletes audio after transcription and source video after completion or expiry.
- Abuse/problem reports are stored without secrets and linked to job/user metadata.
- Local/beta processing can reuse a previous same-user same-URL `source_video` artifact when Aparat returns transient 5xx errors.
- Use `backend/scripts/benchmark_avalai.py` for repeatable STT model comparisons; it must not print API keys.

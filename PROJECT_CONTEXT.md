# Uptube Project Context

## Product
- MVP connects Aparat to YouTube for creators.
- Flow: paste Aparat link, connect YouTube, download video, extract audio, transcribe with Metis Whisper, review/edit SRT text, upload private YouTube video, attach captions, show final link.
- Default language is Persian (`fa`).

## Locked Decisions
- STT provider: Metis Generations API, model `{ "name": "openai", "model": "whisper-1" }`, operation `STT`.
- Metis result retrieval: polling every 5 seconds minimum. Webhook is later.
- Subtitle output: SRT only for MVP. No word-level timestamps or timeline editor.
- Metis currently fails completed jobs when `response_format=srt` is sent; use chunked text transcription and render SRT locally until Metis fixes that runtime bug.
- YouTube privacy: always `private` in MVP.
- Aparat intake: API-first direct MP4 discovery with `yt-dlp` fallback, because no stable official download contract is assumed.
- Ownership gate: user must confirm they own or are allowed to republish the source video.
- Beta limits: max 30 minutes and max 500 MB by default.

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

## External Contracts
- Metis create: `POST https://api.metisai.ir/api/v2/generate`
- Metis poll: `GET https://api.metisai.ir/api/v2/generate/{generation_id}`
- Metis target STT args: `file`, `language`, `response_format=srt`, `temperature=0`; current implementation uses chunked text output and local SRT rendering while Metis SRT output fails.
- YouTube scopes: `youtube.upload` and `youtube.force-ssl`.
- Each completed job should budget at least 500 YouTube quota units.

## Implementation Notes
- Use adapters for Aparat, transcription, artifact storage, and YouTube.
- State changes must create job events.
- User can edit subtitle text only; segment timing stays unchanged.
- Upload starts only after `awaiting_review`.
- Upload UI must keep showing active progress while `uploading_video` or `uploading_caption`.
- Cleanup should delete audio after transcription and source video after completion or expiry.

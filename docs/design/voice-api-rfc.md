# RFC: optional speech transport for the experience MVP

Status: approved by the user for the additive contract change. The authoritative
cross-module shapes are published in `docs/contracts/api.openapi.yaml` version
`1.1.0`; this RFC explains their scope and rationale.

## Purpose and scope

Allow explicit microphone input and spoken NPC replies while preserving the
existing text dialogue and command flow. Speech converts media only; it cannot
create proposals, execute commands, advance ticks, or mutate world state.
ASR, dialogue and TTS providers remain independently replaceable and may run
locally. No cloud endpoint, model or credential is embedded in the client.

## Proposed contract change

After approval, submit a contract-only RFC-style PR changing
`docs/contracts/api.openapi.yaml` info version from `1.0.0` to `1.1.0`.
The URL prefix stays `/v1` because both routes are additive. Existing dialogue,
command, event and snapshot shapes remain unchanged. Implementation follows
that contract as a separate change.

| Operation | Request | Success |
| --- | --- | --- |
| `POST /v1/voice/transcriptions` | Raw `audio/wav` bytes, not JSON/base64 or multipart | `200 application/json`, exactly `{ "text": "…" }` |
| `POST /v1/voice/speech` | `application/json`, exactly `{ "text": "…" }` | `200 audio/wav`, raw bytes |

Transcription accepts a nonempty PCM WAV, 16-bit samples, one or two channels,
8–48 kHz, at most 30 seconds and 6 MiB including headers. Reject malformed,
truncated, unsupported or zero-duration WAV before contacting a provider.
The response text is nonempty and at most 2,000 Unicode characters. Empty or
invalid provider transcription is a provider failure; it never triggers dialogue.

Speech accepts nonempty trimmed text of at most 2,000 Unicode characters.
Return a validated nonempty PCM WAV, 16-bit, one or two channels, 8–48 kHz,
at most 120 seconds and 12 MiB including headers. These bounds are deliberately
narrower than some upstream providers and make playback behavior predictable.
The server caps streamed upstream responses before buffering the full body.

Errors use the existing top-level `{code, message, details}` envelope:

| Status | Code | Meaning |
| --- | --- | --- |
| `413` | `audio_too_large` | Request byte or duration limit exceeded |
| `415` | `unsupported_audio` | Wrong content type, sample format, channels or rate |
| `422` | `invalid_audio` / `invalid_text` | Malformed/empty WAV or invalid JSON/text |
| `502` | `speech_provider_failed` | Upstream error, malformed response or output limit exceeded |
| `503` | `speech_not_configured` | Required provider URL/model/voice is absent |
| `504` | `speech_provider_timeout` | Provider deadline exceeded |

Errors expose neither remote response bodies nor credentials. Every route has
a bounded deadline and performs no implicit paid retry. Missing credentials do
not cause a fallback to a hosted provider. Models that need keys fail clearly;
local compatible servers may work without keys.

## Configuration and lifecycle

The server reads `ASR_BASE_URL`, `ASR_MODEL`, optional `ASR_API_KEY`, and
`TTS_BASE_URL`, `TTS_MODEL`, `TTS_VOICE`, optional `TTS_API_KEY`.
URLs include the provider's `/v1` prefix; upstream calls use compatible
`/audio/transcriptions` and `/audio/speech` routes. Neither endpoint receives a
model, URL or credential from Godot. Provider calls do not hold world DB locks.
Record audio only after an explicit record-button/key action. Show recording
state and a stop/cancel control; automatically stop at 30 seconds. Do not
automatically record on scene load, talk selection or NPC proximity.

The UI puts recognized text into an editable input, then the player sends it
through existing `/v1/dialogue`. The returned ActionProposal is attempted only
through existing `/v1/commands`; only accepted events/snapshots prove effects.
Speak the returned character text separately; TTS failure must not repeat a
dialogue request or command, or hide a successful world result. Label generated
speech as synthetic and retain readable text when sound is unavailable.

Capture a conversation generation, target NPC and world ID on each request.
Cancel/scene exit/world load/target change increments the generation and drops
late ASR/TTS/dialogue responses. Stop playback when cancelled. A cancellation
does not undo a command already submitted: refresh authoritative state instead.
A stale proposal is discarded after a 409 and resync; never silently rebuild
it with the latest state version. Reserve the pending command before allowing
polling/UI traffic to take the client's single HTTP request slot.

Raw recordings and generated audio are transient, not persisted by default.
Explicitly requested experiment captures stay in ignored local output storage.
World events and existing decision audit records remain the evidence for actual
behavior. Speech endpoints do not add an authoritative promise/debt mechanism.

## Validation and acceptance

Before merge, contract checks must cover both added operations, MIME types,
strict JSON shapes, byte/duration/text bounds and all declared errors. Test
provider HTTP requests with an actual localhost stub and adversarial replies,
including timeouts, empty text, invalid WAV, oversized/chunked output and errors
containing a test secret. Verify no secret appears in errors or logs.

Godot runtime tests cover explicit record/stop/cancel, editable transcript,
successful and failed playback, stale responses, a request-slot race, and
cancel-after-command resync. Existing deterministic replay and save/load checks
must still pass. A real microphone, configured model and audible Chinese
response require separate manual validation; stub tests cannot establish speech
recognition accuracy, latency, pronunciation or immersion.

The local `clients/godot-art/` project keeps its independent visual/animation
acceptance. `clients/godot/` proves gameplay and authoritative consequences.
Neither track's success implies the other is complete. Final combined acceptance
requires a real recorded playthrough with speech, NPC choice, command result,
persisted memory and visible world consequence, plus separate art evidence.

## Approval and delivery

The user approved the additive `1.1.0` contract described above. Review its
contract-only diff separately from implementation. No purchase or live paid
service call is authorized by this RFC.

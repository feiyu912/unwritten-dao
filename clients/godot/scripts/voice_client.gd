class_name VoiceClient
extends Node

## Optional media transport only. Never sends dialogue or world commands.
signal transcript_received(text: String)
signal speech_received(wav: PackedByteArray)
signal request_failed(message: String)

const MAX_INPUT_BYTES := 6 * 1024 * 1024
const MAX_OUTPUT_BYTES := 12 * 1024 * 1024

var busy := false
var _base_url := "http://127.0.0.1:8000"
var _generation := 0
var _http: HTTPRequest

func configure(url: String) -> void:
	cancel()
	_base_url = url.trim_suffix("/")

func transcribe(wav: PackedByteArray) -> bool:
	if wav.is_empty() or wav.size() > MAX_INPUT_BYTES:
		request_failed.emit("Recording is empty or too large. Record up to 30 seconds.")
		return false
	return _send("/v1/voice/transcriptions", "transcription", "audio/wav", wav)

func synthesize(text: String) -> bool:
	if text.strip_edges().is_empty() or text.length() > 2000:
		request_failed.emit("This reply cannot be spoken. Its text is still available.")
		return false
	var payload := JSON.stringify({"text": text})
	return _send("/v1/voice/speech", "speech", "application/json", payload.to_utf8_buffer())

func cancel() -> void:
	_generation += 1
	busy = false
	if is_instance_valid(_http):
		_http.cancel_request()
		_http.queue_free()
	_http = null

func _send(path: String, kind: String, mime: String, payload: PackedByteArray) -> bool:
	if busy:
		request_failed.emit("Voice is busy. Finish or cancel the current recording/reply.")
		return false
	_generation += 1
	var generation := _generation
	_http = HTTPRequest.new()
	_http.timeout = 40.0
	_http.body_size_limit = 65536 if kind == "transcription" else MAX_OUTPUT_BYTES
	add_child(_http)
	_http.request_completed.connect(_completed.bind(generation, kind))
	busy = true
	var error := _http.request_raw(
		_base_url + path, PackedStringArray(["Content-Type: " + mime]),
		HTTPClient.METHOD_POST, payload
	)
	if error != OK:
		cancel()
		request_failed.emit("Voice request could not start. Text dialogue remains available.")
		return false
	return true

func _completed(
	result: int, status: int, headers: PackedStringArray, body: PackedByteArray,
	generation: int, kind: String
) -> void:
	if generation != _generation:
		return
	busy = false
	if is_instance_valid(_http):
		_http.queue_free()
	_http = null
	if result != HTTPRequest.RESULT_SUCCESS or status != 200:
		request_failed.emit("Voice unavailable (HTTP %d). Text dialogue remains available." % status)
		return
	if kind == "transcription":
		var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
		if parsed is Dictionary and parsed.get("text") is String:
			var text: String = parsed["text"]
			if not text.strip_edges().is_empty() and text.length() <= 2000:
				transcript_received.emit(text)
				return
		request_failed.emit("No usable transcript was returned. Please try again or type.")
	else:
		var is_wav := false
		for header in headers:
			if header.to_lower().begins_with("content-type:"):
				is_wav = header.to_lower().contains("audio/wav")
		if is_wav and body.size() >= 44:
			speech_received.emit(body)
		else:
			request_failed.emit("No usable NPC audio was returned. The reply text is available.")

func _exit_tree() -> void:
	cancel()

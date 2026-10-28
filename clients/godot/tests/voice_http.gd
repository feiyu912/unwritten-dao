extends SceneTree

## Synthetic audio transport test, not microphone or model-quality evidence.
var _client: VoiceClient
var _transcripts := 0
var _replies := 0
var _finished := false

func _initialize() -> void:
	_start.call_deferred()

func _start() -> void:
	_client = VoiceClient.new()
	_client.configure(OS.get_environment("UNWRITTEN_DAO_VOICE_TEST_URL"))
	root.add_child(_client)
	_client.transcript_received.connect(_on_transcript)
	_client.speech_received.connect(_on_speech)
	_client.request_failed.connect(_fail)
	create_timer(8.0).timeout.connect(func() -> void:
		if not _finished:
			_fail("voice roundtrip timed out")
	)
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = 16000
	stream.stereo = false
	var pcm := PackedByteArray()
	pcm.resize(16000)
	stream.data = pcm
	if not _client.transcribe(VoiceCapture.encode_wav(stream)):
		_fail("transcription did not start")

func _on_transcript(text: String) -> void:
	_transcripts += 1
	if text != "道友，可否借我护符？":
		_fail("incorrect UTF-8 transcript")
		return
	if not _client.synthesize("我愿将护符赠你。"):
		_fail("speech did not start")

func _on_speech(wav: PackedByteArray) -> void:
	_replies += 1
	var decoded := AudioStreamWAV.load_from_buffer(wav)
	if decoded == null or not is_equal_approx(decoded.get_length(), 0.5):
		_fail("invalid WAV response")
		return
	# A late callback from the cancelled generation must not emit a transcript
	# or clear a newer request's busy state.
	var old_generation: int = _client.get("_generation")
	_client.cancel()
	_client.busy = true
	var stale := JSON.stringify({"text": "道友，可否借我护符？"}).to_utf8_buffer()
	_client.call("_completed", HTTPRequest.RESULT_SUCCESS, 200,
		PackedStringArray(["Content-Type: application/json"]), stale,
		old_generation, "transcription")
	if _transcripts != 1 or _replies != 1 or not _client.busy:
		_fail("cancelled response affected current voice state")
		return
	_client.cancel()
	_finished = true
	print("VOICE HTTP roundtrip passed; cancelled generation ignored; no world actions")
	quit(0)

func _fail(message: String) -> void:
	if _finished:
		return
	_finished = true
	printerr("VOICE HTTP failed: " + message)
	quit(1)

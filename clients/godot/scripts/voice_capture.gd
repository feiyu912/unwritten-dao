class_name VoiceCapture
extends Node

## Explicit, bounded microphone capture. No provider credentials or world state.
## No microphone player is started until start_recording() is called by the UI.
signal recording_ready(wav: PackedByteArray)
signal recording_changed(active: bool)
signal capture_failed(message: String)

const MAX_SECONDS := 30.0
const MAX_WAV_BYTES := 12000000

var recording := false
var _elapsed := 0.0
var _bus_name: StringName
var _effect: AudioEffectRecord
var _microphone: AudioStreamPlayer
var _speaker: AudioStreamPlayer

func _ready() -> void:
	_speaker = AudioStreamPlayer.new()
	add_child(_speaker)
	set_process(false)

func start_recording() -> bool:
	if recording:
		return false
	if not ProjectSettings.get_setting("audio/driver/enable_input", false):
		capture_failed.emit("Microphone input is disabled in project settings.")
		return false
	if _microphone == null:
		_create_microphone_bus()
	_speaker.stop()
	_elapsed = 0.0
	_effect.set_recording_active(true)
	_microphone.play()
	recording = true
	set_process(true)
	recording_changed.emit(true)
	return true

func stop_recording() -> void:
	if not recording:
		return
	_microphone.stop()
	_effect.set_recording_active(false)
	recording = false
	set_process(false)
	recording_changed.emit(false)
	var stream := _effect.get_recording()
	if stream == null or stream.get_length() < 0.2:
		capture_failed.emit("Recording too short. Hold the microphone button and speak.")
		return
	var wav := encode_wav(stream)
	if wav.is_empty() or wav.size() > MAX_WAV_BYTES:
		capture_failed.emit("Recording could not be encoded as bounded PCM audio.")
		return
	recording_ready.emit(wav)

func cancel_recording() -> void:
	if not recording:
		return
	_microphone.stop()
	_effect.set_recording_active(false)
	recording = false
	set_process(false)
	recording_changed.emit(false)

func play_reply(wav: PackedByteArray) -> bool:
	if recording or wav.is_empty() or wav.size() > MAX_WAV_BYTES:
		return false
	var stream := AudioStreamWAV.load_from_buffer(wav)
	if stream == null:
		capture_failed.emit("NPC voice returned invalid WAV audio.")
		return false
	_speaker.stream = stream
	_speaker.play()
	return true

func stop_playback() -> void:
	if is_instance_valid(_speaker):
		_speaker.stop()

func _process(delta: float) -> void:
	_elapsed += delta
	if _elapsed >= MAX_SECONDS:
		stop_recording()

func _create_microphone_bus() -> void:
	_bus_name = StringName("VoiceCapture_%d" % get_instance_id())
	AudioServer.add_bus()
	var bus := AudioServer.bus_count - 1
	AudioServer.set_bus_name(bus, _bus_name)
	# Record microphone only; muting prevents local microphone feedback.
	AudioServer.set_bus_mute(bus, true)
	_effect = AudioEffectRecord.new()
	_effect.format = AudioStreamWAV.FORMAT_16_BITS
	AudioServer.add_bus_effect(bus, _effect)
	_microphone = AudioStreamPlayer.new()
	_microphone.stream = AudioStreamMicrophone.new()
	_microphone.bus = _bus_name
	add_child(_microphone)

func _exit_tree() -> void:
	cancel_recording()
	if not _bus_name.is_empty():
		var bus := AudioServer.get_bus_index(_bus_name)
		if bus > 0:
			AudioServer.remove_bus(bus)

static func encode_wav(stream: AudioStreamWAV) -> PackedByteArray:
	if stream.format != AudioStreamWAV.FORMAT_16_BITS:
		return PackedByteArray()
	var channels := 2 if stream.stereo else 1
	if stream.mix_rate < 8000 or stream.mix_rate > 48000:
		return PackedByteArray()
	var pcm := stream.data
	if pcm.is_empty() or pcm.size() % (channels * 2) != 0:
		return PackedByteArray()
	if float(pcm.size()) / (stream.mix_rate * channels * 2) > MAX_SECONDS:
		return PackedByteArray()
	var header := PackedByteArray()
	header.resize(44)
	for chunk in [[0, "RIFF"], [8, "WAVE"], [12, "fmt "], [36, "data"]]:
		var bytes: PackedByteArray = str(chunk[1]).to_ascii_buffer()
		for index in range(4):
			header[int(chunk[0]) + index] = bytes[index]
	header.encode_u32(4, 36 + pcm.size())
	header.encode_u32(16, 16)
	header.encode_u16(20, 1)
	header.encode_u16(22, channels)
	header.encode_u32(24, stream.mix_rate)
	header.encode_u32(28, stream.mix_rate * channels * 2)
	header.encode_u16(32, channels * 2)
	header.encode_u16(34, 16)
	header.encode_u32(40, pcm.size())
	header.append_array(pcm)
	return header

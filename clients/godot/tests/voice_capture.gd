extends SceneTree

func _initialize() -> void:
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = 16000
	stream.stereo = false
	var pcm := PackedByteArray()
	pcm.resize(32000)
	for index in range(16000):
		pcm.encode_s16(index * 2, int(sin(index * 0.1) * 10000.0))
	stream.data = pcm
	var wav := VoiceCapture.encode_wav(stream)
	assert(wav.size() == 32044)
	assert(wav.slice(0, 4).get_string_from_ascii() == "RIFF")
	assert(wav.decode_u32(24) == 16000)
	assert(wav.decode_u16(22) == 1)
	assert(wav.slice(44) == pcm)
	var decoded := AudioStreamWAV.load_from_buffer(wav)
	assert(decoded != null)
	assert(is_equal_approx(decoded.get_length(), 1.0))
	stream.stereo = true
	wav = VoiceCapture.encode_wav(stream)
	assert(wav.decode_u16(22) == 2)
	assert(wav.decode_u32(28) == 64000)
	stream.format = AudioStreamWAV.FORMAT_8_BITS
	assert(VoiceCapture.encode_wav(stream).is_empty())
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = 4000
	assert(VoiceCapture.encode_wav(stream).is_empty())
	stream.mix_rate = 16000
	pcm.resize(16000 * 4 * 31)
	stream.data = pcm
	assert(VoiceCapture.encode_wav(stream).is_empty())
	print("VOICE PCM WAV round-trip and bounds passed (synthetic audio, no microphone)")
	quit(0)

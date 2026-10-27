class_name WorldClient
extends Node

## Presentation-only HTTP client for the authoritative world server.
## It never computes cultivation, combat, death, ownership, or discovery.

signal snapshot_received(snapshot: Dictionary)
signal events_received(events: Array)
signal command_completed(result: Dictionary)
signal dialogue_received(reply: String)
signal request_failed(message: String)
signal resync_required()

@export var base_url: String = "http://127.0.0.1:8000"

var world_id: String = ""
var player_id: String = ""
var tick: int = 0
var state_version: int = 0
var last_event_id: int = 0
var busy: bool = false

var _http: HTTPRequest

func _ready() -> void:
	_http = HTTPRequest.new()
	_http.timeout = 15.0
	add_child(_http)
	_http.request_completed.connect(_on_request_completed)

func configure(url: String) -> void:
	base_url = url.trim_suffix("/")

func fetch_snapshot() -> bool:
	return _request("/v1/world/snapshot", "snapshot")

func fetch_events() -> bool:
	return _request("/v1/world/events?after=%d&limit=200" % last_event_id, "events")

func send_command(command_type: String, arguments: Dictionary, actor_id: String = "") -> bool:
	if busy or world_id.is_empty():
		return false
	var actor_value: Variant = null if actor_id.is_empty() else actor_id
	var command := {
		"schema_version": "world-command.v1",
		"command_id": _uuid4(),
		"idempotency_key": "godot:%s:%s" % [command_type, _uuid4()],
		"world_id": world_id,
		"actor_id": actor_value,
		"issued_tick": tick,
		"expected_state_version": state_version,
		"type": command_type,
		"arguments": arguments,
		"source": "player" if not actor_id.is_empty() else "system",
	}
	return _request("/v1/commands", "command", command)

func send_dialogue(npc_id: String, message: String) -> bool:
	if player_id.is_empty():
		return false
	var payload := {"npc_id": npc_id, "player_id": player_id, "message": message}
	return _request("/v1/dialogue", "dialogue", payload)

func _request(path: String, kind: String, payload: Dictionary = {}) -> bool:
	if busy:
		return false
	busy = true
	_http.set_meta("request_kind", kind)
	var headers := PackedStringArray()
	var method: HTTPClient.Method = HTTPClient.METHOD_GET
	var body := ""
	if not payload.is_empty():
		method = HTTPClient.METHOD_POST
		body = JSON.stringify(payload)
		headers.append("Content-Type: application/json")
	var error := _http.request(base_url + path, headers, method, body)
	if error != OK:
		busy = false
		request_failed.emit("HTTPRequest failed to start: %d" % error)
		return false
	return true

func _on_request_completed(
	_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray
) -> void:
	busy = false
	var kind: String = str(_http.get_meta("request_kind", ""))
	var text := body.get_string_from_utf8()
	var parsed: Variant = JSON.parse_string(text)
	if response_code == 409:
		resync_required.emit()
		call_deferred("fetch_snapshot")
		return
	if response_code >= 400 or parsed == null:
		request_failed.emit("HTTP %d: %s" % [response_code, text.left(240)])
		return
	match kind:
		"snapshot":
			_apply_snapshot(parsed)
		"events":
			var rows: Array = parsed.get("events", [])
			if not rows.is_empty():
				last_event_id = int(rows[-1].get("event_id", last_event_id))
				events_received.emit(rows)
		"command":
			var result: Dictionary = parsed
			state_version = int(result.get("state_version", state_version))
			command_completed.emit(result)
		"dialogue":
			dialogue_received.emit(str(parsed.get("reply_text", "")))
		_:
			request_failed.emit("unknown response kind: %s" % kind)

func _apply_snapshot(snapshot: Dictionary) -> void:
	world_id = str(snapshot.get("world_id", ""))
	tick = int(snapshot.get("tick", 0))
	state_version = int(snapshot.get("state_version", 0))
	last_event_id = int(snapshot.get("last_event_id", 0))
	var state: Dictionary = snapshot.get("state", {})
	player_id = str(state.get("player_id", ""))
	snapshot_received.emit(snapshot)

func _uuid4() -> String:
	var bytes := Crypto.new().generate_random_bytes(16)
	bytes[6] = (bytes[6] & 0x0f) | 0x40
	bytes[8] = (bytes[8] & 0x3f) | 0x80
	var hex := bytes.hex_encode()
	return "%s-%s-%s-%s-%s" % [
		hex.substr(0, 8), hex.substr(8, 4), hex.substr(12, 4),
		hex.substr(16, 4), hex.substr(20, 12),
	]

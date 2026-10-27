extends SceneTree

## Optional live-server smoke test. Requires a running world server; not part
## of CI. Set UNWRITTEN_DAO_API to override the default base URL.
## Run: godot --headless --path clients/godot --script res://tests/smoke_server.gd

var _client: WorldClient
var _sent := false
var _failed := false

func _initialize() -> void:
	var url := OS.get_environment("UNWRITTEN_DAO_API")
	_client = WorldClient.new()
	if not url.is_empty():
		_client.configure(url)
	root.add_child(_client)
	_client.snapshot_received.connect(_on_snapshot)
	_client.command_completed.connect(_on_command)
	_client.request_failed.connect(_on_failure)
	_client.fetch_snapshot.call_deferred()

func _on_snapshot(snapshot: Dictionary) -> void:
	var state: Dictionary = snapshot.get("state", {})
	print("SMOKE snapshot tick=%d version=%d npcs=%d player=%s" % [
		_client.tick, _client.state_version, state.get("npcs", {}).size(), _client.player_id,
	])
	if _sent:
		return
	_sent = true
	_client.send_command("advance_time", {"ticks": 1}, "")

func _on_command(result: Dictionary) -> void:
	print("SMOKE command ok version=%d events=%d" % [
		int(result.get("state_version", 0)), result.get("events", []).size(),
	])
	quit(0 if not _failed else 1)

func _on_failure(message: String) -> void:
	_failed = true
	printerr("SMOKE failed: %s" % message)
	quit(1)
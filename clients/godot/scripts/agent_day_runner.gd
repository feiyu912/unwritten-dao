class_name AgentDayRunner
extends Node

## Explicit next-day orchestration over existing server APIs. No local rules.
## Cancelling prevents future requests; already committed commands remain real.
## The owner must suspend other uses of the shared client while active.
signal day_completed(snapshot: Dictionary)
signal snapshot_updated(snapshot: Dictionary)
signal failed(message: String)

var active := false
var _client: WorldClient
var _phase := ""
var _world_id := ""
var _npc_ids: Array = []
var _index := 0
var _current_npc_id := ""
var _snapshot: Dictionary = {}

func configure(client: WorldClient) -> void:
	if _client != null:
		return
	_client = client
	_client.snapshot_received.connect(_on_snapshot)
	_client.command_completed.connect(_on_command)
	_client.decision_received.connect(_on_decision)
	_client.request_failed.connect(_on_failure)
	_client.resync_required.connect(_on_resync)

func start() -> bool:
	if active or _client == null or _client.busy:
		return false
	active = true
	_phase = "initial"
	_world_id = ""
	_npc_ids.clear()
	_index = 0
	if not _client.fetch_snapshot():
		_on_failure("Could not read the world before advancing the day.")
		return false
	return true

func cancel() -> void:
	active = false
	_phase = ""
	_current_npc_id = ""

func _on_snapshot(snapshot: Dictionary) -> void:
	if not active or _phase not in ["initial", "refresh", "final"]:
		return
	var world_id := str(snapshot.get("world_id", ""))
	if world_id.is_empty() or (not _world_id.is_empty() and world_id != _world_id):
		_on_failure("The world changed during this day. Refresh before continuing.")
		return
	_world_id = world_id
	_snapshot = snapshot
	var state: Dictionary = snapshot.get("state", {})
	if _phase == "initial":
		_npc_ids = state.get("npcs", {}).keys()
		_npc_ids.sort()
		_npc_ids.erase(str(state.get("player_id", _client.player_id)))
	if _phase == "final":
		cancel()
		day_completed.emit(snapshot)
		return
	_phase = "next"
	snapshot_updated.emit(snapshot)
	_prepare_next.call_deferred()

func _prepare_next() -> void:
	if not active or _phase != "next":
		return
	var state: Dictionary = _snapshot.get("state", {})
	var npcs: Dictionary = state.get("npcs", {})
	while _index < _npc_ids.size():
		_current_npc_id = str(_npc_ids[_index])
		_index += 1
		var npc: Dictionary = npcs.get(_current_npc_id, {})
		if not npc.get("alive", false) or npc.get("active_action") != null:
			continue
		_phase = "decision"
		if not _client.request_decision(_current_npc_id):
			_on_failure("Could not request an NPC decision. The day stopped.")
		return
	_phase = "advance"
	if not _client.send_command("advance_time", {"ticks": 1}, ""):
		_on_failure("Could not advance time. Refresh before continuing.")

func _on_decision(proposal: Dictionary) -> void:
	if not active or _phase != "decision":
		return
	if str(proposal.get("npc_id", "")) != _current_npc_id:
		_on_failure("An NPC proposal belonged to a different character. The day stopped.")
		return
	if int(proposal.get("observed_world_version", -1)) != _client.state_version:
		_on_failure("An NPC proposal expired. Refresh before continuing.")
		return
	_phase = "action"
	if not _client.submit_dialogue_proposal(proposal):
		_on_failure("The NPC action could not be submitted. The day stopped.")

func _on_command(result: Dictionary) -> void:
	if not active or _phase not in ["action", "advance"]:
		return
	if not result.get("accepted", false):
		_on_failure("The world rejected an action. Refresh before continuing.")
		return
	_phase = "final" if _phase == "advance" else "refresh"
	if not _client.fetch_snapshot():
		_on_failure("Could not refresh the changed world. The day stopped.")

func _on_failure(message: String) -> void:
	if not active:
		return
	cancel()
	failed.emit(message)

func _on_resync() -> void:
	_on_failure("The world changed during an action. Refresh before continuing.")

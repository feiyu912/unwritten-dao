extends Node3D

## Godot vertical slice: renders authoritative snapshots and submits commands.
## It never computes game rules locally.

const SCENE_DATA_PATH := "res://data/mvp_scene.json"
const CM_TO_M := 0.01
const PLAYER_SPEED := 6.0
const LOCATION_SEND_RADIUS := 3.5

@onready var world_root: Node3D = $WorldRoot
@onready var player: CharacterBody3D = $Player
@onready var camera: Camera3D = $Camera3D
@onready var status_label: Label = $UI/Root/VBox/StatusLabel
@onready var event_log: RichTextLabel = $UI/Root/VBox/EventLog
@onready var dialogue_edit: LineEdit = $UI/Root/VBox/DialogueRow/DialogueEdit
@onready var talk_button: Button = $UI/Root/VBox/DialogueRow/TalkButton
@onready var resync_button: Button = $UI/Root/VBox/DialogueRow/ResyncButton

var client: WorldClient
var layout: Dictionary = {}
var state: Dictionary = {}
var npc_views: Dictionary = {}
var location_positions: Dictionary = {}
var current_location_id: String = ""
var _location_cooldown: float = 0.0
var _poll_elapsed: float = 0.0

func _ready() -> void:
	_parse_layout()
	_spawn_locations()
	_spawn_npcs()
	client = WorldClient.new()
	client.configure("http://127.0.0.1:8000")
	add_child(client)
	client.snapshot_received.connect(_on_snapshot)
	client.events_received.connect(_on_events)
	client.command_completed.connect(_on_command_completed)
	client.dialogue_received.connect(_on_dialogue)
	client.request_failed.connect(_on_request_failed)
	client.resync_required.connect(_on_resync_required)
	talk_button.pressed.connect(_talk)
	resync_button.pressed.connect(_resync)
	dialogue_edit.text_submitted.connect(func(_text: String) -> void: _talk())
	_append_log("[color=#8fd3ff]Connecting to world server…[/color]")
	client.fetch_snapshot()
	_move_player_to_spawn()

func _process(delta: float) -> void:
	_move_player(delta)
	_follow_camera()
	_location_cooldown = maxf(0.0, _location_cooldown - delta)
	_poll_elapsed += delta
	if _poll_elapsed >= 1.0:
		_poll_elapsed = 0.0
		if not client.busy:
			client.fetch_events()

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("take"):
		_take()
	elif event.is_action_pressed("investigate"):
		_investigate()
	elif event.is_action_pressed("enter_realm"):
		_enter_realm()
	elif event.is_action_pressed("claim"):
		_claim()
	elif event.is_action_pressed("talk"):
		_talk()
	elif event.is_action_pressed("next_day"):
		_next_day()
	elif event.is_action_pressed("resync"):
		_resync()

func _parse_layout() -> void:
	var text := FileAccess.get_file_as_string(SCENE_DATA_PATH)
	var parsed: Variant = JSON.parse_string(text)
	if parsed is Dictionary:
		layout = parsed
	else:
		_append_log("[color=#ff8080]Cannot read layout JSON[/color]")

func _spawn_locations() -> void:
	for location in layout.get("locations", []):
		var xy: Array = location.get("coordinates_xy_cm", [0, 0])
		var pos := Vector3(float(xy[0]) * CM_TO_M, 0.0, float(xy[1]) * CM_TO_M)
		location_positions[str(location["location_id"])] = pos
		var marker := MeshInstance3D.new()
		var box := BoxMesh.new()
		box.size = Vector3(4.0, 0.2, 4.0)
		marker.mesh = box
		marker.position = pos
		world_root.add_child(marker)
		var label := Label3D.new()
		label.text = str(location.get("display_name", location["location_id"]))
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.font_size = 40
		label.position = pos + Vector3(0, 1.2, 0)
		world_root.add_child(label)

func _spawn_npcs() -> void:
	for spawn in layout.get("npc_spawns", []):
		var view := NpcView.new()
		var xy: Array = spawn.get("coordinates_xy_cm", [0, 0])
		view.position = Vector3(float(xy[0]) * CM_TO_M, 0.0, float(xy[1]) * CM_TO_M)
		view.setup(spawn)
		world_root.add_child(view)
		npc_views[str(spawn["npc_id"])] = view

func _move_player_to_spawn() -> void:
	var spawn: Dictionary = layout.get("player_spawn", {})
	var xy: Array = spawn.get("coordinates_xy_cm", [0, 0])
	player.position = Vector3(float(xy[0]) * CM_TO_M, 1.0, float(xy[1]) * CM_TO_M)

func _move_player(delta: float) -> void:
	var input := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var velocity := Vector3(input.x, 0, input.y) * PLAYER_SPEED
	player.velocity = velocity
	player.move_and_slide()
	if velocity.length() > 0.1:
		_try_enter_location()

func _follow_camera() -> void:
	var target := player.position + Vector3(0, 8, 10)
	camera.position = camera.position.lerp(target, 0.15)
	camera.look_at(player.position + Vector3(0, 1, 0))

func _try_enter_location() -> void:
	if _location_cooldown > 0.0 or client.busy or current_location_id.is_empty():
		return
	var nearest_id := ""
	var nearest := 1e9
	for location_id in location_positions:
		var distance: float = player.position.distance_to(location_positions[location_id])
		if distance < nearest:
			nearest = distance
			nearest_id = location_id
	if nearest_id.is_empty() or nearest > LOCATION_SEND_RADIUS or nearest_id == current_location_id:
		return
	_location_cooldown = 2.0
	client.send_command("move", {"to_location_id": nearest_id}, client.player_id)

func _current_location() -> Dictionary:
	var locations: Dictionary = state.get("locations", {})
	return locations.get(current_location_id, {})

func _take() -> void:
	var stash: Array = _current_location().get("stash", [])
	if stash.is_empty():
		_append_log("Nothing to take here.")
		return
	var item_id := str(stash[0])
	client.send_command("transfer_item", {
		"item_id": item_id,
		"from": {"kind": "location", "id": current_location_id},
		"to": {"kind": "npc", "id": client.player_id},
	}, client.player_id)

func _investigate() -> void:
	client.send_command("investigate", {
		"target_location_id": current_location_id,
		"focus": "secret_realm",
	}, client.player_id)

func _enter_realm() -> void:
	var realms: Dictionary = state.get("secret_realms", {})
	for realm_id in realms:
		var realm: Dictionary = realms[realm_id]
		var discovered: Array = realm.get("discovered_by", [])
		if realm.get("entrance_location_id") == current_location_id and client.player_id in discovered:
			client.send_command("enter_secret_realm", {"realm_id": realm_id}, client.player_id)
			return
	_append_log("No discovered realm entrance here.")

func _claim() -> void:
	var opportunities: Dictionary = state.get("opportunities", {})
	for opportunity_id in opportunities:
		var opportunity: Dictionary = opportunities[opportunity_id]
		if opportunity.get("location_id") == current_location_id and opportunity.get("claimed_by") == null:
			client.send_command("claim_opportunity", {"opportunity_id": opportunity_id}, client.player_id)
			return
	_append_log("No visible opportunity here.")

func _talk() -> void:
	var message := dialogue_edit.text.strip_edges()
	if message.is_empty() or client.player_id.is_empty():
		return
	var npcs: Dictionary = state.get("npcs", {})
	for npc_id in npcs:
		var npc: Dictionary = npcs[npc_id]
		if npc_id != client.player_id and npc.get("location_id") == current_location_id and npc.get("alive", false):
			client.send_dialogue(npc_id, message)
			dialogue_edit.text = ""
			return
	_append_log("Nobody here to talk to.")

func _next_day() -> void:
	client.send_command("advance_time", {"ticks": 1}, "")

func _resync() -> void:
	_append_log("Resyncing authoritative snapshot…")
	client.fetch_snapshot()

func _on_snapshot(snapshot: Dictionary) -> void:
	state = snapshot.get("state", {})
	var npcs: Dictionary = state.get("npcs", {})
	var player_npc: Dictionary = npcs.get(client.player_id, {})
	current_location_id = str(player_npc.get("location_id", ""))
	for npc_id in npc_views:
		if npcs.has(npc_id):
			npc_views[npc_id].apply_snapshot(npcs[npc_id])
	var locations: Dictionary = state.get("locations", {})
	var location_name := str(locations.get(current_location_id, {}).get("name", current_location_id))
	status_label.text = "tick %d · %s · 境界 %s 层 %s · 气血 %s · 灵石 %s · npcs %d" % [
		client.tick, location_name, player_npc.get("realm", 0), player_npc.get("stage", 1),
		player_npc.get("health", 0.0), player_npc.get("wealth", 0), npcs.size(),
	]

func _on_events(events: Array) -> void:
	for event in events:
		_append_log("[%d] %s" % [int(event.get("tick", 0)), str(event.get("type", ""))])
	if not client.busy:
		client.fetch_snapshot()

func _on_command_completed(result: Dictionary) -> void:
	for event in result.get("events", []):
		_append_log("[color=#9fe3b0]%s[/color]" % str(event.get("type", "")))
	client.fetch_snapshot()

func _on_dialogue(reply: String) -> void:
	_append_log("[color=#e9d18a]%s[/color]" % reply)

func _on_request_failed(message: String) -> void:
	_append_log("[color=#ff8080]%s[/color]" % message)

func _on_resync_required() -> void:
	_append_log("[color=#ffcc66]409: state advanced, resyncing[/color]")

func _append_log(line: String) -> void:
	event_log.append_text(line + "\n")
	var lines := event_log.get_parsed_text().split("\n")
	if lines.size() > 120:
		event_log.text = "\n".join(lines.slice(lines.size() - 120))

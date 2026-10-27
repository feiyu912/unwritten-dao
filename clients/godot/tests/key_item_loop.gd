extends SceneTree

## Drives the canonical key-item loop through the real HTTP client against a
## fresh world: map fragment -> investigate -> secret realm -> foundation pill.
## Requires a running server with a tick-0 world; not part of CI.
## Run: godot --headless --path clients/godot --script res://tests/key_item_loop.gd

const MAP_ITEM := "item_map_fragment"
const TEMPLE := "location_ruined_temple"
const VALLEY := "location_misty_valley"
const CAVE := "location_ancient_cave"
const PILL := "item_foundation_pill"

var _client: WorldClient
var _state: Dictionary = {}
var _player_id := ""
var _realm_id := ""

func _initialize() -> void:
	var url := OS.get_environment("UNWRITTEN_DAO_API")
	_client = WorldClient.new()
	if not url.is_empty():
		_client.configure(url)
	root.add_child(_client)
	_client.request_failed.connect(_on_failure)
	_run.call_deferred()

func _run() -> void:
	_client.fetch_snapshot()
	var snapshot: Dictionary = await _client.snapshot_received
	_state = snapshot.get("state", {})
	_player_id = _client.player_id
	var player: Dictionary = _state.get("npcs", {}).get(_player_id, {})
	print("GODOT LOOP start tick=%d player=%s at=%s" % [
		_client.tick, _player_id, str(player.get("location_id", "")),
	])
	var error := await _play()
	if error.is_empty():
		quit(0)
	else:
		_fail(error)

func _play() -> String:
	var error := await _take_map()
	if not error.is_empty():
		return error
	error = await _open_realm()
	if not error.is_empty():
		return error
	error = await _take_pill()
	if not error.is_empty():
		return error
	return await _verify()

func _take_map() -> String:
	var error := await _travel_to(TEMPLE)
	if not error.is_empty():
		return error
	var result := await _command("transfer_item", {
		"item_id": MAP_ITEM,
		"from": {"kind": "location", "id": TEMPLE},
		"to": {"kind": "npc", "id": _player_id},
	})
	if _first_event(result, "ITEM_TRANSFERRED").is_empty():
		return "map fragment was not transferred"
	print("GODOT LOOP took the map at the temple")
	return ""

func _open_realm() -> String:
	var error := await _travel_to(VALLEY)
	if not error.is_empty():
		return error
	var investigated := await _command("investigate", {
		"target_location_id": VALLEY,
		"focus": "secret_realm",
	})
	if _first_event(investigated, "SECRET_REALM_DISCOVERED").is_empty():
		return "secret realm was not discovered"
	_realm_id = _realm_at(VALLEY)
	if _realm_id.is_empty():
		return "no realm keyed to %s" % VALLEY
	var entered := await _command("enter_secret_realm", {"realm_id": _realm_id})
	if _first_event(entered, "SECRET_REALM_ENTERED").is_empty():
		return "secret realm was not entered"
	print("GODOT LOOP discovered and entered %s" % _realm_id)
	return ""

func _take_pill() -> String:
	var opportunity_id := _opportunity_at(CAVE)
	if opportunity_id.is_empty():
		return "no unclaimed opportunity in the ancient cave"
	for _attempt in range(10):
		var result := await _command("claim_opportunity", {"opportunity_id": opportunity_id})
		if result.is_empty():
			return "claim command did not complete"
		for event in result.get("events", []):
			if str(event.get("type", "")) != "OPPORTUNITY_CLAIMED":
				continue
			var payload: Dictionary = event.get("payload", {})
			if payload.get("success") is bool and payload["success"]:
				var rewards: Array = payload.get("reward_item_ids", [])
				if PILL in rewards:
					print("GODOT LOOP claimed the foundation pill")
					return ""
				return "claim succeeded without the pill"
	return "pill was not awarded in 10 claim attempts"

func _verify() -> String:
	_client.fetch_snapshot()
	var final: Dictionary = await _client.snapshot_received
	var final_state: Dictionary = final.get("state", {})
	var player: Dictionary = final_state.get("npcs", {}).get(_player_id, {})
	var inventory: Array = player.get("inventory", [])
	var has_pill: bool = PILL in inventory
	var realm: Dictionary = final_state.get("secret_realms", {}).get(_realm_id, {})
	var discovered: Array = realm.get("discovered_by", [])
	print("GODOT LOOP OK tick=%d version=%d pill=%s discovered_by=%s" % [
		_client.tick,
		_client.state_version,
		str(has_pill),
		str(_player_id in discovered),
	])
	return "" if has_pill else "final snapshot does not contain the pill"

func _travel_to(goal: String) -> String:
	await _refresh()
	var player: Dictionary = _state.get("npcs", {}).get(_player_id, {})
	var current := str(player.get("location_id", ""))
	for target in _route(_state.get("locations", {}), current, goal):
		var moved := await _command("move", {"to_location_id": target})
		if moved.is_empty():
			return "move to %s did not complete" % target
	print("GODOT LOOP reached %s" % goal)
	return ""

func _refresh() -> void:
	_client.fetch_snapshot()
	var snapshot: Dictionary = await _client.snapshot_received
	_state = snapshot.get("state", {})

func _command(intent: String, arguments: Dictionary) -> Dictionary:
	if not _client.send_command(intent, arguments, _client.player_id):
		return {}
	return await _client.command_completed

func _first_event(result: Dictionary, event_type: String) -> Dictionary:
	for event in result.get("events", []):
		if str(event.get("type", "")) == event_type:
			return event
	return {}

func _realm_at(location_id: String) -> String:
	for realm_key in _state.get("secret_realms", {}):
		var realm: Dictionary = _state["secret_realms"][realm_key]
		if realm.get("entrance_location_id") == location_id:
			return str(realm_key)
	return ""

func _opportunity_at(location_id: String) -> String:
	for opportunity_key in _state.get("opportunities", {}):
		var opportunity: Dictionary = _state["opportunities"][opportunity_key]
		if opportunity.get("location_id") != location_id:
			continue
		if opportunity.get("claimed_by") == null and not opportunity.get("expired", false):
			return str(opportunity_key)
	return ""

func _route(locations: Dictionary, start: String, goal: String) -> Array:
	var previous := {start: ""}
	var frontier: Array = [start]
	while not frontier.is_empty():
		var current: String = frontier.pop_front()
		if current == goal:
			break
		var location: Dictionary = locations.get(current, {})
		for adjacent in location.get("adjacency", []):
			if not previous.has(adjacent):
				previous[adjacent] = current
				frontier.append(adjacent)
	var path: Array = []
	var step := goal
	while step != start and previous.has(step) and step != "":
		path.push_front(step)
		step = previous[step]
	return path

func _fail(message: String) -> void:
	printerr("GODOT LOOP failed: %s" % message)
	quit(1)

func _on_failure(message: String) -> void:
	_fail("request: %s" % message)
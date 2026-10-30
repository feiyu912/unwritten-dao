extends SceneTree

## Client-visible contention after one autonomous day.
## The Godot client drives NPC decisions through WorldClient, then reads the
## authoritative /v1/world/events page and reports the event types it received.
## This is transport/visibility evidence, not from-seed reachability or render proof.

var _client: WorldClient
var _runner: AgentDayRunner
var _finished := false

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	_client = WorldClient.new()
	_client.configure(OS.get_environment("UNWRITTEN_DAO_AGENT_TEST_URL"))
	root.add_child(_client)
	_client.events_received.connect(_on_events)
	_client.request_failed.connect(func(message: String) -> void:
		printerr("CONTENTION request_failed: " + message)
		_fail(message)
	)
	_runner = AgentDayRunner.new()
	root.add_child(_runner)
	_runner.configure(_client)
	_runner.day_completed.connect(_on_day)
	_runner.failed.connect(_fail)
	create_timer(30.0).timeout.connect(func() -> void:
		if not _finished:
			printerr("CONTENTION debug tick=%d busy=%s active=%s" % [
				_client.tick, str(_client.busy), str(_runner.active)
			])
			_fail("contention day timed out")
	)
	if not _runner.start():
		_fail("contention day did not start")
	else:
		print("CONTENTION started url=%s" % _client.base_url)

func _on_day(_snapshot: Dictionary) -> void:
	if _runner.active or _client.tick != 1:
		_fail("day did not finish at tick 1")
		return
	# The runner's last snapshot moved the incremental cursor to the newest
	# event. Rewind it to read the whole authoritative page for this day.
	_client.last_event_id = 0
	if not _client.fetch_events():
		_fail("could not read authoritative events")

func _on_events(rows: Array) -> void:
	if _finished:
		return
	var types: Array[String] = []
	for row in rows:
		types.append(str(row.get("type", "")))
	var found: Array[String] = []
	for wanted in ["OPPORTUNITY_CLAIMED", "COMBAT_RESOLVED", "RELATIONSHIP_CHANGED"]:
		if wanted in types:
			found.append(wanted)
	if "OPPORTUNITY_CLAIMED" not in found or "COMBAT_RESOLVED" not in found:
		printerr("CONTENTION failed: claim/combat not visible in %s" % str(types))
		_finished = true
		quit(1)
		return
	_finished = true
	print("CONTENTION SEEN tick=%d events=%d types=%s" % [
		_client.tick, types.size(), ",".join(types)
	])
	quit(0)

func _fail(message: String) -> void:
	if _finished:
		return
	_finished = true
	printerr("CONTENTION failed: " + message)
	quit(1)


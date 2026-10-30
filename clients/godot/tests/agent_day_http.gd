extends SceneTree

## Actual HTTP orchestration against a Python core-backed in-memory server.
## Does not claim PostgreSQL, paid model, rendering or FPS verification.
var _client: WorldClient
var _runner: AgentDayRunner
var _finished := false

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	_client = WorldClient.new()
	_client.configure(OS.get_environment("UNWRITTEN_DAO_AGENT_TEST_URL"))
	root.add_child(_client)
	_runner = AgentDayRunner.new()
	root.add_child(_runner)
	_runner.configure(_client)
	_runner.day_completed.connect(_on_day)
	_runner.failed.connect(_fail)
	create_timer(25.0).timeout.connect(func() -> void:
		if not _finished:
			_fail("autonomous day timed out")
	)
	if not _runner.start():
		_fail("autonomous day did not start")

func _on_day(snapshot: Dictionary) -> void:
	if _runner.active or _client.tick != 1 or int(snapshot.get("tick", -1)) != 1:
		_fail("day did not finish with a one-tick authoritative snapshot")
		return
	if int(snapshot.get("state_version", -1)) != _client.state_version:
		_fail("client did not retain authoritative version")
		return
	_finished = true
	print("AGENT HTTP day passed tick=1 checksum=%s" % snapshot.get("checksum", ""))
	quit(0)

func _fail(message: String) -> void:
	if _finished:
		return
	_finished = true
	printerr("AGENT HTTP failed: " + message)
	quit(1)

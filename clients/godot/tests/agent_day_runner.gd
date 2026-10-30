extends SceneTree

## Orchestration doubles only: does not claim server or simulation verification.
class ProbeClient extends WorldClient:
	var calls: Array[String] = []
	var reads := 0
	var reject_decision := false
	var wrong_identity := false
	var stale_proposal := false

	func _ready() -> void:
		player_id = "player"

	func fetch_snapshot() -> bool:
		calls.append("snapshot")
		reads += 1
		var npcs := {
			"player": {"alive": true}, "z_dead": {"alive": false},
			"b_busy": {"alive": true, "active_action": {"type": "move"}},
			"c": {"alive": reads == 1}, "a": {"alive": true},
		}
		var snapshot := {"world_id": "world", "state_version": state_version,
			"state": {"player_id": player_id, "npcs": npcs}}
		snapshot_received.emit.call_deferred(snapshot)
		return true

	func request_decision(npc_id: String) -> bool:
		calls.append("decision:" + npc_id)
		if reject_decision:
			request_failed.emit.call_deferred("decision unavailable")
		else:
			decision_received.emit.call_deferred({
				"npc_id": "other" if wrong_identity else npc_id,
				"observed_world_version": state_version - 1 if stale_proposal else state_version,
			})
		return true

	func submit_dialogue_proposal(proposal: Dictionary) -> bool:
		calls.append("apply:" + str(proposal["npc_id"]))
		state_version += 1
		command_completed.emit.call_deferred({"accepted": true})
		return true

	func send_command(kind: String, _arguments: Dictionary, _actor: String = "") -> bool:
		calls.append(kind)
		state_version += 1
		command_completed.emit.call_deferred({"accepted": true})
		return true

var _finished := false

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	create_timer(5.0).timeout.connect(func() -> void:
		if not _finished:
			printerr("AGENT DAY test timeout")
			quit(1)
	)
	var probe := ProbeClient.new()
	root.add_child(probe)
	var runner := AgentDayRunner.new()
	root.add_child(runner)
	runner.configure(probe)
	runner.start()
	await runner.day_completed
	if runner.active or probe.calls != ["snapshot", "decision:a", "apply:a",
		"snapshot", "advance_time", "snapshot"]:
		printerr("AGENT DAY wrong sequence: ", probe.calls)
		quit(1)
		return
	probe.calls.clear()
	probe.reject_decision = true
	runner.start()
	await runner.failed
	if runner.active or probe.calls != ["snapshot", "decision:a"]:
		printerr("AGENT DAY retried after failure")
		quit(1)
		return
	probe.calls.clear()
	probe.reject_decision = false
	for wrong_identity in [true, false]:
		probe.wrong_identity = wrong_identity
		probe.stale_proposal = not wrong_identity
		runner.start()
		await runner.failed
		if runner.active or probe.calls != ["snapshot", "decision:a"]:
			printerr("AGENT DAY submitted mismatched or stale proposal")
			quit(1)
			return
		probe.calls.clear()
	probe.stale_proposal = false
	runner.start()
	runner.cancel()
	await process_frame
	await process_frame
	if probe.calls != ["snapshot"] or runner.active:
		printerr("AGENT DAY scheduled after cancellation")
		quit(1)
		return
	_finished = true
	print("AGENT DAY stable order, fresh eligibility, failure and cancellation passed")
	quit(0)

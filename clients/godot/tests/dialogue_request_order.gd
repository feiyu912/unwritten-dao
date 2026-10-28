extends SceneTree

## Regression: callbacks/polling must not steal an NPC action's request slot.
class ProbeClient extends WorldClient:
	var sent: Array[Dictionary] = []

	func _request(path: String, kind: String, payload: Dictionary = {}) -> bool:
		if busy:
			return false
		busy = true
		sent.append({"path": path, "kind": kind, "payload": payload})
		return true

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var client := ProbeClient.new()
	root.add_child(client)
	client.world_id = "world-test"
	client.state_version = 3
	client.tick = 7
	client.busy = true
	client._http.set_meta("request_kind", "dialogue")
	client.dialogue_received.connect(func(_reply: String) -> void:
		assert(not client.fetch_events(), "Polling stole the command request slot")
	)
	var proposal := {
		"proposal_id": "11111111-1111-4111-8111-111111111111",
		"npc_id": "npc-test", "observed_world_version": 3,
		"intent": "move", "arguments": {"to_location_id": "destination"},
	}
	var body := JSON.stringify({"reply_text": "我愿前往。", "proposal": proposal})
	client._on_request_completed(HTTPRequest.RESULT_SUCCESS, 200, [], body.to_utf8_buffer())
	assert(client.sent.size() == 1)
	assert(client.sent[0]["path"] == "/v1/commands")
	var command: Dictionary = client.sent[0]["payload"]
	assert(command["source"] == "agent")
	assert(command["actor_id"] == "npc-test")
	assert(command["expected_state_version"] == 3)
	assert(command["command_id"] == proposal["proposal_id"])
	client.busy = false
	client.state_version = 4
	assert(not client.submit_dialogue_proposal(proposal))
	assert(client.sent.size() == 2)
	assert(client.sent[1]["kind"] == "snapshot")
	for days in [30.0, 1.5]:
		client.busy = false
		var numeric: Dictionary = proposal.duplicate(true)
		numeric["observed_world_version"] = client.state_version
		numeric["intent"] = "start_cultivation"
		numeric["arguments"] = {"days": days}
		assert(client.submit_dialogue_proposal(numeric))
		var submitted: Variant = client.sent[-1]["payload"]["arguments"]["days"]
		assert(typeof(submitted) == (TYPE_INT if days == 30.0 else TYPE_FLOAT))
		assert(submitted == days)
	client.queue_free()
	print("DIALOGUE request reservation and stale proposal checks passed (no server)")
	quit(0)

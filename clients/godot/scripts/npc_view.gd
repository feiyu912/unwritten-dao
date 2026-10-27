extends Node3D
class_name NpcView

## Presentation-only actor keyed by the authoritative npc_id.

var npc_id: String = ""
var canonical_role: String = ""
var _mesh: MeshInstance3D
var _label: Label3D
var _alive: bool = true
var _base_y: float = 0.0
var _phase: float = 0.0

func setup(data: Dictionary) -> void:
	npc_id = str(data.get("npc_id", ""))
	canonical_role = str(data.get("canonical_role", ""))
	name = "NPC_%s" % npc_id.substr(0, 8)
	_base_y = position.y
	_phase = float(absi(npc_id.hash()) % 100) / 100.0

	var capsule := CapsuleMesh.new()
	capsule.radius = 0.35
	capsule.height = 1.6
	_mesh = MeshInstance3D.new()
	_mesh.mesh = capsule
	_mesh.position.y = 0.9
	add_child(_mesh)
	_set_color(_color_for_role(canonical_role))

	_label = Label3D.new()
	_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	_label.no_depth_test = true
	_label.font_size = 32
	_label.position.y = 2.1
	_label.text = str(data.get("name", npc_id.substr(0, 8)))
	add_child(_label)

func apply_snapshot(npc: Dictionary) -> void:
	_alive = bool(npc.get("alive", true))
	var realm := int(npc.get("realm", 0))
	var stage := int(npc.get("stage", 1))
	var display := str(npc.get("name", npc_id.substr(0, 8)))
	_label.text = "%s\n境界 %d 层 %d%s" % [display, realm, stage, "" if _alive else " · 已故"]
	visible = _alive
	if _mesh:
		_set_color(_color_for_role(canonical_role, _alive))

func _process(delta: float) -> void:
	if not _alive:
		return
	_phase += delta * 1.6
	position.y = _base_y + sin(_phase) * 0.05

func _set_color(color: Color, alive: bool = true) -> void:
	var material := StandardMaterial3D.new()
	material.albedo_color = color if alive else Color(0.25, 0.25, 0.28)
	_mesh.material_override = material

func _color_for_role(role: String, alive: bool = true) -> Color:
	if not alive:
		return Color(0.25, 0.25, 0.28)
	match role:
		"player":
			return Color(0.95, 0.85, 0.35)
		"protagonist":
			return Color(0.35, 0.75, 0.95)
		"sect_leader", "alchemist_elder", "inner_disciple", "deacon":
			return Color(0.45, 0.6, 0.95)
		"enemy_leader", "rival", "chixiao_deacon", "chixiao_disciple":
			return Color(0.9, 0.4, 0.4)
		_:
			return Color(0.6, 0.65, 0.7)

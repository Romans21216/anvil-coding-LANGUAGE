"""Shared compiler data types, constants, naming, and source paths."""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime" / "anvil_runtime.c"
INCLUDE = ROOT / "runtime"
MAX_BLOCK_DEPTH = 128


@dataclass
class Node:
    kind: str
    line: int
    value: str = ""
    name: str = ""
    body: list["Node"] = field(default_factory=list)
    otherwise: list["Node"] = field(default_factory=list)
    params: list[str] = field(default_factory=list)
    locals: set[str] = field(default_factory=set)
    local_arrays: dict[str, int] = field(default_factory=dict)
    local_array_lines: dict[str, int] = field(default_factory=dict)
    source: pathlib.Path | None = None
    string: bool = False
    declared_type: str | None = None


class ArrayDeclarations(dict):
    """Global array sizes with their original declaration locations."""

    def __init__(self):
        super().__init__()
        self.locations: dict[str, tuple[pathlib.Path, int]] = {}


@dataclass
class ParsedProgram:
    """Syntax tree plus unresolved references awaiting semantic validation."""

    path: pathlib.Path
    functions: dict[str, Node]
    top: list[Node]
    variables: set[str]
    arrays: dict[str, int]
    variable_references: list[tuple[str, int, str | None, pathlib.Path]]
    local_references: list[tuple[str, int, str | None, pathlib.Path]]
    # Names that came from `library import`, so a library file can tell its own
    # functions from the ones it pulled in.
    library_functions: set[str] = field(default_factory=set)


def decode_string(raw: str) -> str:
    """Decode an Anvil string literal token (including quotes) into text."""
    inner = raw[1:-1]
    decoded = []
    index = 0
    escapes = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
    while index < len(inner):
        char = inner[index]
        if char == "\\" and index + 1 < len(inner):
            decoded.append(escapes.get(inner[index + 1], char + inner[index + 1]))
            index += 2
        else:
            decoded.append(char)
            index += 1
    return "".join(decoded)


class CompileError(Exception):
    pass


def constant_truth(value: str) -> bool | None:
    """True/False when the text is a bare numeric literal, else None.

    Only literals qualify: anything with an operator or a name can have effects
    or depend on runtime state, so those keep their runtime evaluation.
    """
    text = (value or "").strip()
    if not re.fullmatch(r"[-+]?[0-9]+(?:\.[0-9]+)?", text):
        return None
    return float(text) != 0.0


def c_name(name: str) -> str:
    return "anvil_" + re.sub(r"[^A-Za-z0-9_]", "_", name)


def variable_code(name: str, scope: Node | None = None) -> str:
    if scope and name in scope.params:
        return c_name(scope.name + "__" + name)
    return c_name(name)


def array_size(name: str, scope: Node | None, arrays: dict[str, int]) -> int | None:
    if scope is not None and name in scope.local_arrays:
        return scope.local_arrays[name]
    return arrays.get(name)


def array_code(name: str, scope: Node | None) -> str:
    if scope is not None and name in scope.local_arrays:
        return c_name(scope.name + "__" + name)
    return c_name(name)


RUNTIME_C_NAMES = {
    "anvil_run",
    "anvil_divide",
    "anvil_check_number",
    "anvil_set_scene3d",
    "anvil_camera_perspective",
    "anvil_camera2d",
    "anvil_parallax",
    "anvil_dpi_scale",
    "anvil_window_scale",
    "anvil_camera_angle",
    "anvil_mesh_culled",
    "anvil_mesh_drawn",
    "anvil_mesh_culling",
    "anvil_shadow",
    "anvil_shadow_height",
    "anvil_shadow_alpha",
    "anvil_clear",
    "anvil_rect",
    "anvil_particle_emit",
    "anvil_particle_count",
    "anvil_particle_clear",
    "anvil_particle_gravity",
    "anvil_circle",
    "anvil_line",
    "anvil_cube",
    "anvil_sphere",
    "anvil_plane",
    "anvil_text",
    "anvil_text_width",
    "anvil_text_wrap",
    "anvil_text_number",
    "anvil_time",
    "anvil_frame_tick",
    "anvil_frame_render",
    "anvil_frame_present",
    "anvil_delta",
    "anvil_pressed",
    "anvil_held",
    "anvil_mouse_x",
    "anvil_mouse_y",
    "anvil_mouse_pressed",
    "anvil_mouse_held",
    "anvil_mouse_wheel",
    "anvil_image_load",
    "anvil_image_load_site",
    "anvil_sound_load_site",
    "anvil_memory_report",
    "anvil_tilemap_new",
    "anvil_tilemap_free",
    "anvil_tilemap_columns",
    "anvil_tilemap_rows",
    "anvil_tilemap_tiles",
    "anvil_tilemap_set",
    "anvil_tilemap_get",
    "anvil_tilemap_fill",
    "anvil_tilemap_area",
    "anvil_tilemap_draw",
    "anvil_tilemap_solid",
    "anvil_tilemap_is_solid",
    "anvil_tilemap_cell",
    "anvil_tilemap_collide",
    "anvil_tilemap_animate",
    "anvil_tilemap_frame",
    "anvil_tilemap_error",
    "anvil_image_width",
    "anvil_buffer",
    "anvil_frame_capture",
    "anvil_sprite_batch",
    "anvil_sprite_depth",
    "anvil_sprite_queued",
    "anvil_image_pixel",
    "anvil_image_height",
    "anvil_image_destroy",
    "anvil_image_draw",
    "anvil_image_draw_scaled",
    "anvil_image_draw_rotated",
    "anvil_image_draw_region",
    "anvil_image_tint",
    "anvil_image_flip",
    "anvil_sound_error",
    "anvil_sound_load",
    "anvil_sound_play",
    "anvil_sound_play_loop",
    "anvil_sound_stop",
    "anvil_sound_stop_all",
    "anvil_sound_group",
    "anvil_sound_group_volume",
    "anvil_sound_group_mute",
    "anvil_sound_group_gain",
    "anvil_sound_group_stop",
    "anvil_music_load",
    "anvil_music_play",
    "anvil_music_play_loop",
    "anvil_music_stop",
    "anvil_music_playing",
    "anvil_music_volume",
    "anvil_music_position",
    "anvil_music_length",
    "anvil_music_error",
    "anvil_sound_volume",
    "anvil_sound_pan",
    "anvil_sound_pitch",
    "anvil_sound_active",
    "anvil_sound_duration",
    "anvil_sound_rms",
    "anvil_sound_destroy",
    "anvil_save_error",
    "anvil_set_project",
    "anvil_save_number",
    "anvil_load_number",
    "anvil_save_text",
    "anvil_load_text",
    "anvil_save_exists",
    "anvil_save_delete",
    "anvil_rnd",
    "anvil_seed",
    "anvil_noise",
    "anvil_fbm",
    "anvil_net_host",
    "anvil_net_join",
    "anvil_net_send",
    "anvil_net_receive",
    "anvil_net_close",
    "anvil_array_get",
    "anvil_array_set",
    "anvil_local_array_alloc",
    "anvil_local_array_free",
    "anvil_ray_backend",
    "anvil_ray_backend_available",
    "anvil_body_create",
    "anvil_body_create_box",
    "anvil_body_destroy",
    "anvil_body_active",
    "anvil_body_x",
    "anvil_body_y",
    "anvil_body_vx",
    "anvil_body_vy",
    "anvil_body_set_velocity",
    "anvil_body_force",
    "anvil_body_restitution",
    "anvil_body_friction",
    "anvil_body_collision",
    "anvil_physics_capacity",
    "anvil_physics_gravity",
    "anvil_physics_step",
    "anvil_frame_enter",
    "anvil_frame_leave",
}

MAX_ARRAY_SIZE = 1_048_576

MAX_LOCAL_ARRAY_ELEMENTS = 8_192

MAX_ACTIVE_LOCAL_ARRAY_BYTES = 16 * 1024 * 1024

LANGUAGE_VERSION = 1

KEY_CODES = {
    **{chr(code): code for code in range(ord("A"), ord("Z") + 1)},
    "SPACE": 32, "LEFT": 37, "UP": 38, "RIGHT": 39, "DOWN": 40,
    "ENTER": 13, "ESCAPE": 27,
}

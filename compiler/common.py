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


class CompileError(Exception):
    pass


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
    "anvil_set_fixed_hz",
    "anvil_camera_fov",
    "anvil_camera_control",
    "anvil_trace_sphere",
    "anvil_trace_finish",
    "anvil_camera_perspective",
    "anvil_clear",
    "anvil_rect",
    "anvil_circle",
    "anvil_line",
    "anvil_cube",
    "anvil_sphere",
    "anvil_plane",
    "anvil_text",
    "anvil_text_number",
    "anvil_time",
    "anvil_delta",
    "anvil_pressed",
    "anvil_held",
    "anvil_mouse_x",
    "anvil_mouse_y",
    "anvil_mouse_pressed",
    "anvil_mouse_held",
    "anvil_mouse_wheel",
    "anvil_image_load",
    "anvil_image_width",
    "anvil_image_height",
    "anvil_image_destroy",
    "anvil_image_draw",
    "anvil_image_draw_scaled",
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

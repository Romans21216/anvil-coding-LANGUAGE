"""Extension functions: callables that live outside the Anvil program.

An extension is a small JSON manifest next to a library:

    {
      "name": "mathx",
      "kind": "dll",
      "dll": "mathx.dll",
      "lib": "mathx.lib",
      "functions": [
        {"name": "gcd", "symbol": "anvil_ext_gcd", "arity": 2},
        {"name": "lcm", "symbol": "anvil_ext_lcm", "arity": 2}
      ]
    }

A C++ extension exports ``extern "C" __declspec(dllexport) double
anvil_ext_x(double ...)``; a C# extension exports the same symbol through
``[UnmanagedCallersOnly(EntryPoint = "anvil_ext_x")]`` once published with
NativeAOT, so both arrive as a DLL with a C ABI. ``kind: "anvil"`` points at a
``.ANVL`` file instead and needs no DLL at all.

Registering an extension makes its names callable like builtins (``gcd(48, 18)``)
on both backends and gives the compiler the libraries to link and the DLLs to
place beside the executable.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field


class ExtensionError(Exception):
    """A manifest is malformed, or it collides with something already defined."""


@dataclass(frozen=True)
class ExtensionFunction:
    name: str
    symbol: str
    arity: int


@dataclass(frozen=True)
class Extension:
    name: str
    kind: str
    path: pathlib.Path
    dll: pathlib.Path | None = None
    lib: pathlib.Path | None = None
    source: pathlib.Path | None = None
    functions: tuple[ExtensionFunction, ...] = field(default_factory=tuple)

    def symbols(self) -> dict[str, ExtensionFunction]:
        return {function.name: function for function in self.functions}


ACTIVE: dict[str, Extension] = {}
_NAME = __import__("re").compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


_INSTALLED: set[str] = set()


def reset() -> None:
    """Drop every registered extension (tests call this between programs)."""
    _uninstall_builtins()
    ACTIVE.clear()


def _uninstall_builtins() -> None:
    """Remove the names a previous registration installed."""
    from compiler import native_codegen
    from compiler.expressions import BUILTINS, BUILTIN_C_NAMES

    for name in list(_INSTALLED):
        BUILTINS.pop(name, None)
        BUILTIN_C_NAMES.pop(name, None)
        native_codegen.NativeCodegen.BUILTIN_NAMES.discard(name)
    _INSTALLED.clear()


def load_manifest(path: pathlib.Path) -> Extension:
    path = pathlib.Path(path).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ExtensionError(f"{path}: cannot read extension manifest: {error}") from error
    except json.JSONDecodeError as error:
        raise ExtensionError(f"{path}:{error.lineno}: invalid JSON: {error.msg}") from error

    name = data.get("name")
    if not isinstance(name, str) or not _NAME.match(name):
        raise ExtensionError(f"{path}: extension needs a name like 'mathx'")

    kind = data.get("kind", "dll")
    if kind not in ("dll", "anvil"):
        raise ExtensionError(f"{path}: kind must be 'dll' or 'anvil', got {kind!r}")

    base = path.parent
    functions = []
    raw_functions = data.get("functions")
    if not isinstance(raw_functions, list) or not raw_functions:
        raise ExtensionError(f"{path}: functions must be a non-empty list")
    for entry in raw_functions:
        if not isinstance(entry, dict):
            raise ExtensionError(f"{path}: each function must be an object")
        function_name = entry.get("name")
        if not isinstance(function_name, str) or not _NAME.match(function_name):
            raise ExtensionError(f"{path}: function name {function_name!r} is not an identifier")
        arity = entry.get("arity")
        if not isinstance(arity, int) or arity < 0 or arity > 4:
            raise ExtensionError(
                f"{path}: {function_name} needs an arity between 0 and 4 "
                "(numbers cross the extension boundary in XMM0-3)"
            )
        if kind == "dll":
            symbol = entry.get("symbol")
            if not isinstance(symbol, str) or not _NAME.match(symbol):
                raise ExtensionError(f"{path}: {function_name} needs an exported symbol")
        else:
            symbol = function_name
        functions.append(ExtensionFunction(function_name, symbol, arity))

    dll = lib = source = None
    if kind == "dll":
        raw_dll = data.get("dll")
        if not isinstance(raw_dll, str) or not raw_dll:
            raise ExtensionError(f"{path}: a dll extension needs a dll path")
        dll = (base / raw_dll).resolve()
        if not dll.is_file():
            raise ExtensionError(f"{path}: dll not found: {dll}")
        raw_lib = data.get("lib")
        if raw_lib:
            lib = (base / raw_lib).resolve()
            if not lib.is_file():
                raise ExtensionError(f"{path}: import library not found: {lib}")
    else:
        raw_source = data.get("source")
        if not isinstance(raw_source, str) or not raw_source:
            raise ExtensionError(f"{path}: an anvil extension needs a source path")
        source = (base / raw_source).resolve()
        if not source.is_file():
            raise ExtensionError(f"{path}: anvil source not found: {source}")

    return Extension(name, kind, path, dll, lib, source, tuple(functions))


def register(extension: Extension) -> None:
    from compiler.expressions import BUILTINS

    if extension.name in ACTIVE:
        raise ExtensionError(f"extension {extension.name!r} is already registered")
    for function in extension.functions:
        if function.name in BUILTINS:
            raise ExtensionError(
                f"extension {extension.name!r} wants {function.name!r}, "
                "which is already a builtin"
            )
        for other in ACTIVE.values():
            if function.name in other.symbols():
                raise ExtensionError(
                    f"{function.name!r} is already provided by extension {other.name!r}"
                )
    ACTIVE[extension.name] = extension
    _install_builtins()


def load(paths) -> list[Extension]:
    registered = []
    for path in paths:
        extension = load_manifest(pathlib.Path(path))
        register(extension)
        registered.append(extension)
    return registered


def _install_builtins() -> None:
    """Make every extension function a builtin name for both front ends."""
    from compiler import native_codegen
    from compiler.expressions import BUILTINS, BUILTIN_C_NAMES

    _uninstall_builtins()
    for extension in ACTIVE.values():
        if extension.kind != "dll":
            # Anvil-sourced extensions are ordinary functions: call fn(name, ...).
            continue
        for function in extension.functions:
            BUILTINS[function.name] = (function.arity, function.arity)
            BUILTIN_C_NAMES[function.name] = function.symbol
            native_codegen.NativeCodegen.BUILTIN_NAMES.add(function.name)
            _INSTALLED.add(function.name)


def extension_functions() -> dict[str, tuple[Extension, ExtensionFunction]]:
    found = {}
    for extension in ACTIVE.values():
        for function in extension.functions:
            found[function.name] = (extension, function)
    return found


def c_declarations() -> list[str]:
    """``__declspec(dllimport)`` lines for the generated C preamble."""
    lines = []
    for name, (extension, function) in sorted(extension_functions().items()):
        if extension.kind != "dll":
            continue
        params = ", ".join("double" for _ in range(function.arity)) or "void"
        lines.append(f'__declspec(dllimport) double {function.symbol}({params});')
    return lines


def ensure_import_libraries(compiler: pathlib.Path) -> None:
    """Build a .lib for any DLL extension that shipped without one.

    A NativeAOT C# library and a hand-built DLL often arrive with no import
    library, and the C backend needs one to link. ``lib.exe`` sits next to the
    compiler, so the manifest only has to name the exports.
    """
    import subprocess

    lib_tool = pathlib.Path(compiler).parent / "lib.exe"
    for extension in list(ACTIVE.values()):
        if extension.kind != "dll" or extension.lib is not None:
            continue
        if not lib_tool.is_file():
            raise ExtensionError(
                f"{extension.path}: {extension.dll.name} has no import library and "
                f"lib.exe was not found beside {compiler}"
            )
        definition = extension.path.parent / (extension.dll.stem + ".def")
        exports = chr(10).join(f'  {f.symbol}' for f in extension.functions)
        definition_text = (
            f'LIBRARY {extension.dll.stem}' + chr(10)
            + 'EXPORTS' + chr(10)
            + exports + chr(10)
        )
        definition.write_text(definition_text, encoding='utf-8')
        library = extension.path.parent / (extension.dll.stem + ".lib")
        result = subprocess.run(
            [
                str(lib_tool),
                "/nologo",
                f"/def:{definition}",
                "/machine:x64",
                f"/out:{library}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not library.is_file():
            raise ExtensionError(
                f"{extension.path}: could not build an import library for "
                f"{extension.dll.name}: {(result.stdout + result.stderr).strip()}"
            )
        ACTIVE[extension.name] = Extension(
            extension.name,
            extension.kind,
            extension.path,
            extension.dll,
            library,
            extension.source,
            extension.functions,
        )


def libraries() -> list[pathlib.Path]:
    return [e.lib for e in ACTIVE.values() if e.lib is not None]


def dlls() -> list[pathlib.Path]:
    return [e.dll for e in ACTIVE.values() if e.dll is not None]


def anvil_sources() -> list[pathlib.Path]:
    return [e.source for e in ACTIVE.values() if e.source is not None]

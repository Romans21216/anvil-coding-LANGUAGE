"""Semantic checks over the parser's unresolved program representation."""

from __future__ import annotations

from compiler.common import CompileError, ParsedProgram, RUNTIME_C_NAMES, c_name


def validate_program(program: ParsedProgram) -> None:
    """Resolve variable references and validate generated C symbol ownership."""
    path = program.path
    functions = program.functions
    variables = program.variables
    arrays = program.arrays
    if not functions:
        raise CompileError(f"{path}: define at least one fn(name) function")

    for name, line_no, function_name in program.variable_references:
        fn = functions.get(function_name) if function_name else None
        if name not in variables and (fn is None or name not in fn.params):
            raise CompileError(
                f"{path}:{line_no}: unknown variable {name!r}; assign it with set var({name}) first"
            )
    for name, line_no, function_name in program.local_references:
        fn = functions.get(function_name) if function_name else None
        if fn is None or name not in fn.locals:
            raise CompileError(
                f"{path}:{line_no}: unknown local variable {name!r}; declare it with set local({name}) first"
            )
    for fn in functions.values():
        for name in fn.local_arrays:
            if name in fn.params or name in fn.locals:
                raise CompileError(
                    f"{path}:{fn.line}: local array {name!r} conflicts with a local variable or parameter in function '{fn.name}'"
                )

    c_symbols: dict[str, tuple[str, str]] = {}
    symbols = (
        [(name, "variable") for name in variables]
        + [(name, "function") for name in functions]
        + [(name, "array") for name in arrays]
    )
    for fn in functions.values():
        symbols.extend(
            (fn.name + "__" + name, "function-local")
            for name in fn.params + sorted(fn.locals) + sorted(fn.local_arrays)
        )
    for name, kind in sorted(symbols):
        generated = c_name(name)
        if generated in RUNTIME_C_NAMES:
            raise CompileError(
                f"{path}: identifier {name!r} conflicts with a reserved runtime name"
            )
        previous = c_symbols.get(generated)
        if previous is not None:
            previous_name, previous_kind = previous
            if previous_name != name:
                raise CompileError(
                    f"{path}: identifiers {previous_name!r} and {name!r} both map to C name {generated!r}"
                )
            if previous_kind != kind:
                raise CompileError(
                    f"{path}: {kind} {name!r} conflicts with another declaration of the same name"
                )
        c_symbols[generated] = (name, kind)

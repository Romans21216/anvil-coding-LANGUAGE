"""Semantic checks over the parser's unresolved program representation."""

from __future__ import annotations

from compiler.common import CompileError, MAX_BLOCK_DEPTH, ParsedProgram, RUNTIME_C_NAMES, c_name


def validate_program(program: ParsedProgram, *, check_symbols: bool = True) -> None:
    """Resolve variable references and validate generated C symbol ownership."""
    path = program.path
    functions = program.functions
    variables = program.variables
    arrays = program.arrays
    if not functions:
        raise CompileError(f"{path}: define at least one fn(name) function")

    pending = [(node, 0) for node in program.top]
    pending.extend((node, 0) for fn in functions.values() for node in fn.body)
    while pending:
        node, depth = pending.pop()
        if node.kind in ("if", "while", "for"):
            depth += 1
            if depth > MAX_BLOCK_DEPTH:
                raise CompileError(f"{node.source or path}:{node.line}: statement nesting exceeds {MAX_BLOCK_DEPTH} blocks")
        pending.extend((child, depth) for child in node.body)
        pending.extend((child, depth) for child in node.otherwise)

    for name, line_no, function_name, source in program.variable_references:
        fn = functions.get(function_name) if function_name else None
        if name not in variables and (fn is None or name not in fn.params):
            raise CompileError(
                f"{source}:{line_no}: unknown variable {name!r}; assign it "
                f"with set var({name}) first"
            )
    for name, line_no, function_name, source in program.local_references:
        fn = functions.get(function_name) if function_name else None
        if fn is None or name not in fn.locals:
            raise CompileError(
                f"{source}:{line_no}: unknown local variable {name!r}; "
                f"declare it with set local({name}) first"
            )
    for fn in functions.values():
        for name in fn.local_arrays:
            if name in fn.params or name in fn.locals:
                raise CompileError(
                    f"{fn.source or path}:"
                    f"{fn.local_array_lines.get(name, fn.line)}: "
                    f"local array {name!r} conflicts with "
                    f"a local variable or parameter in function '{fn.name}'"
                )

    if not check_symbols:
        return  # module source names are checked after compiler-owned binding

    variable_sites = {}
    for reference, line, owner, source in program.variable_references:
        scope = functions.get(owner)
        if scope is None or reference not in scope.params:
            variable_sites.setdefault(reference, (source or path, line))
    local_sites = {}
    for reference, line, owner, source in program.local_references:
        local_sites.setdefault((owner, reference), (source or path, line))

    def variable_site(name):
        return variable_sites.get(name, (path, None))

    def local_site(fn, name):
        if name in fn.local_arrays:
            return fn.source or path, fn.local_array_lines.get(name, fn.line)
        if name in fn.params:
            return fn.source or path, fn.line
        return local_sites.get((fn.name, name), (fn.source or path, fn.line))

    def location(source, line):
        return f"{source}:{line}" if line is not None else str(source)

    c_symbols = {}
    symbols = (
        [(name, "variable", *variable_site(name)) for name in variables]
        + [
            (name, "function", fn.source or path, fn.line)
            for name, fn in functions.items()
        ]
        + [
            (name, "array", *getattr(arrays, "locations", {}).get(name, (path, None)))
            for name in arrays
        ]
    )
    for fn in functions.values():
        symbols.extend(
            (fn.name + "__" + name, "function-local", *local_site(fn, name))
            for name in fn.params + sorted(fn.locals) + sorted(fn.local_arrays)
        )
    for name, kind, source, line in sorted(symbols):
        where = location(source, line)
        generated = c_name(name)
        if generated in RUNTIME_C_NAMES:
            raise CompileError(
                f"{where}: identifier {name!r} conflicts with a reserved runtime name"
            )
        previous = c_symbols.get(generated)
        if previous is not None:
            previous_name, previous_kind, previous_source, previous_line = previous
            if previous_name != name:
                raise CompileError(
                    f"{where}: identifiers {previous_name!r} and {name!r} "
                    f"both map to C name {generated!r}; other declaration at "
                    f"{location(previous_source, previous_line)}"
                )
            if previous_kind != kind:
                raise CompileError(
                    f"{where}: {kind} {name!r} conflicts with another "
                    "declaration of the same name at "
                    f"{location(previous_source, previous_line)}"
                )
        c_symbols[generated] = (name, kind, source, line)

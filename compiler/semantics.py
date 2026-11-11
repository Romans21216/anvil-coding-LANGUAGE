"""Semantic checks over the parser's unresolved program representation."""

from __future__ import annotations

from __future__ import annotations

import re

from compiler.common import CompileError, MAX_BLOCK_DEPTH, ParsedProgram, RUNTIME_C_NAMES, c_name
from compiler.expressions import split_amp


def _walk_all(nodes):
    # Iterative: deeply nested statements must hit the block-depth limit with a
    # CompileError, not a Python RecursionError inside classification.
    pending = list(nodes)
    while pending:
        node = pending.pop()
        yield node
        pending.extend(node.body)
        pending.extend(node.otherwise)


_TEXT_FUNCTION_CALL = re.compile(r"call\s+fn\(([^,)]*)")


def _call_returns_text(program: ParsedProgram, value: str) -> bool:
    match = _TEXT_FUNCTION_CALL.match(value.strip())
    if match is None:
        return False
    target = program.functions.get(match.group(1).strip())
    return bool(target is not None and getattr(target, "returns_text", False))


def _classify_text_functions(program: ParsedProgram, string_vars: set[str]) -> bool:
    """Mark functions whose `output` returns text (the C backend returns char*)."""
    var_pattern = re.compile(r"var\(([A-Za-z_][\w-]*)\)")

    def is_text(value: str) -> bool:
        value = value.strip()
        if not value:
            return False
        if value.startswith('"'):
            return True
        if "&" in value:
            return True
        if re.match(r"(upper|lower|chr|trim|char|mid|left|right)\s*\(", value):
            return True
        match = var_pattern.fullmatch(value)
        if match is not None and match.group(1) in string_vars:
            return True
        return _call_returns_text(program, value)

    changed = False
    for name, fn in program.functions.items():
        if name in ("main", "draw", "update"):
            # Entry and engine callbacks keep a numeric return: main's value is
            # the program result and the engine ignores draw/update results.
            continue
        if getattr(fn, "returns_text", False):
            continue
        for node in _walk_all(fn.body):
            if node.kind == "output" and is_text(node.value):
                fn.returns_text = True
                changed = True
                break
    return changed


def _classify_string_variables(program: ParsedProgram, strict: bool = True) -> set[str]:
    """Mark `set` nodes that assign text and return the variable names.

    An assignment is text when its value starts with a literal, joins values
    with `&`, or copies another text variable. Classification runs to a
    fixpoint so chains like `set var(b) = var(a)` resolve regardless of order.
    """
    import re as _re

    nodes = list(_walk_all(program.top))
    for function in program.functions.values():
        nodes.extend(_walk_all(function.body))
    var_pattern = _re.compile(r"var\(([A-Za-z_][\w-]*)\)")

    def segment_is_text(segment: str) -> bool:
        """A join is text when any part is: a literal, a text builtin, a text
        variable, or a call to a function that returns text."""
        segment = segment.strip()
        if not segment:
            return False
        if segment.startswith('"'):
            return True
        if _re.fullmatch(
            r"(upper|lower|chr|trim|char|mid|left|right)\s*\(.*\)", segment, _re.DOTALL
        ):
            return True
        match = var_pattern.fullmatch(segment)
        if match is not None and match.group(1) in string_vars:
            return True
        return _call_returns_text(program, segment)

    string_vars: set[str] = set()
    changed = True
    while changed:
        changed = False
        for node in nodes:
            if node.kind != "set":
                continue
            value = node.value.strip()
            segments = split_amp(value)
            if len(segments) > 1:
                # `&` is the text-join operator, so any joined value is text —
                # even `1 & 2`, which reads "12". Classifying only joins that
                # contain a literal disagreed with the expression parser and
                # rejected `set var(n) = 1 & 2` as "expected number".
                is_text = True
            else:
                is_text = segment_is_text(value)
            node.string = is_text
            if is_text and node.name not in string_vars:
                string_vars.add(node.name)
                changed = True
    if strict:
        for node in nodes:
            if node.kind == "set" and node.string != (node.name in string_vars):
                raise CompileError(
                    f"{node.source or program.path}:{node.line}: variable "
                    f"'{node.name}' cannot mix text and numbers"
                )
    # Ask targets follow the variable's established kind: numeric when the
    # program assigns numbers to it, text otherwise (the common first case).
    numeric_assigned = {
        node.name for node in nodes if node.kind == "set" and not node.string
    }
    for node in nodes:
        if node.kind == "ask" and node.params:
            node.string = node.params[0] not in numeric_assigned
            if node.string:
                string_vars.add(node.params[0])
    for node in nodes:
        if node.kind == "set" and node.string != (node.name in string_vars):
            raise CompileError(
                f"{node.source or program.path}:{node.line}: variable "
                f"'{node.name}' cannot mix text and numbers"
            )
    from compiler.expressions import STRING_VARIABLES
    STRING_VARIABLES.clear()
    STRING_VARIABLES.update(string_vars)
    return string_vars


def validate_program(program: ParsedProgram) -> None:
    """Resolve variable references and validate generated C symbol ownership."""
    path = program.path
    functions = program.functions
    variables = program.variables
    arrays = program.arrays
    for _ in range(4):
        _classify_string_variables(program, strict=False)
        changed = _classify_text_functions(program, _classify_string_variables(program, strict=False))
        if not changed:
            break
    string_vars = _classify_string_variables(program, strict=True)
    _classify_text_functions(program, string_vars)
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
            if fn is not None and name in fn.locals:
                raise CompileError(
                    f"{source}:{line_no}: {name!r} is a local variable here; "
                    f"write local({name}) instead of var({name})"
                )
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
                    f"{path}:{fn.line}: local array {name!r} conflicts with "
                    f"a local variable or parameter in function '{fn.name}'"
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
                    f"{path}: identifiers {previous_name!r} and {name!r} "
                    f"both map to C name {generated!r}"
                )
            if previous_kind != kind:
                raise CompileError(
                    f"{path}: {kind} {name!r} conflicts with another "
                    "declaration of the same name"
                )
        c_symbols[generated] = (name, kind)

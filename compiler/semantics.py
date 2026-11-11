"""Semantic checks over the parser's unresolved program representation."""

from __future__ import annotations

import re

from compiler.common import CompileError, MAX_BLOCK_DEPTH, ParsedProgram, RUNTIME_C_NAMES, c_name
from compiler.expressions import STRING_VARIABLES, split_amp, split_args


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

    def is_text(value: str, fn=None) -> bool:
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
        if match is not None and fn is not None:
            if match.group(1) in getattr(fn, "text_params", set()):
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
            if node.kind == "output" and is_text(node.value, fn):
                fn.returns_text = True
                changed = True
                break
    return changed


def _find_calls(value: str):
    """Yield (function name, argument text) for every `call fn(...)` in a value."""
    index = 0
    marker = "call fn("
    while True:
        start = value.find(marker, index)
        if start < 0:
            return
        cursor = start + len(marker) - 1
        depth = 0
        while cursor < len(value):
            if value[cursor] == "(":
                depth += 1
            elif value[cursor] == ")":
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        inner = value[start + len(marker):cursor]
        parts = split_args(inner)
        if parts:
            yield parts[0].strip(), parts[1:]
        index = cursor + 1


def _argument_is_text(program: ParsedProgram, raw: str, scope) -> bool:
    value = raw.strip()
    if not value:
        return False
    if value.startswith('"'):
        return True
    if len(split_amp(value)) > 1:
        return True
    match = re.fullmatch(r"var\(([A-Za-z_][\w-]*)\)", value)
    if match is not None:
        name = match.group(1)
        if name in STRING_VARIABLES:
            return True
        if scope is not None and name in scope.params:
            return name in getattr(scope, "text_params", set())
        return False
    if re.match(r"(?:upper|lower|chr|trim|char|mid|left|right)\s*\(", value):
        return True
    target = None
    for call_name, _args in _find_calls(value):
        target = program.functions.get(call_name)
        break
    return bool(target is not None and getattr(target, "returns_text", False))


def _classify_text_params(program: ParsedProgram) -> None:
    """Decide which parameters are text.

    Two sources agree: a parameter is text when the body forces text (a text
    builtin argument, a comparison with a text literal, or returning it directly
    from a text-returning function), and when a call site passes text for it.
    Call-site evidence runs to a fixpoint so `fn(tag, mark, n)` keeps `n` a
    number when every caller passes a number.
    """
    numeric_use = re.compile(
        r"(?:var\([A-Za-z_][\w-]*\)\s*[-+*/%]|[-+*/%]\s*var\([A-Za-z_][\w-]*\))"
    )
    for fn in program.functions.values():
        fn.text_params = set()
        forced_numeric = set()
        for node in _walk_all(fn.body):
            value = (node.value or "").strip()
            if not value:
                continue
            for param in fn.params:
                token = f"var({param})"
                if token not in value:
                    continue
                # Arithmetic involving THIS parameter (not just any arithmetic
                # elsewhere in the same expression) makes it numeric.
                pattern = (
                    rf"var\({param}\)\s*[-+*/%]|[-+*/%]\s*var\({param}\)"
                )
                if re.search(pattern, value):
                    forced_numeric.add(param)
        fn.numeric_params = forced_numeric

    text_call = re.compile(
        r"\b(?:upper|lower|trim|len|ord|number|char|mid|left|right|contains|"
        r"starts_with|ends_with)\s*\(\s*var\(([A-Za-z_][\w-]*)\)"
    )
    text_compare = re.compile(r'(?:=|==|!=|<=|>=|<|>)\s*"')

    nodes = list(_walk_all(program.top))
    for function in program.functions.values():
        nodes.extend((node, function) for node in _walk_all(function.body))

    changed = True
    while changed:
        changed = False
        for entry in nodes:
            node, scope = entry if isinstance(entry, tuple) else (entry, None)
            value = (node.value or "").strip()
            if not value:
                continue
            params = scope.params if scope is not None else []
            if scope is not None:
                for param in params:
                    if getattr(scope, "numeric_params", None) is None:
                        pass
                for match in text_call.finditer(value):
                    if match.group(1) in params and match.group(1) not in scope.text_params:
                        scope.text_params.add(match.group(1))
                        changed = True
                if text_compare.search(value):
                    for param in params:
                        if f"var({param})" in value and param not in scope.text_params:
                            scope.text_params.add(param)
                            changed = True
                if getattr(scope, "returns_text", False) and node.kind == "output":
                    for param in params:
                        if value == f"var({param})" and param not in scope.text_params:
                            scope.text_params.add(param)
                            changed = True
            for call_name, args in _find_calls(value):
                target = program.functions.get(call_name)
                if target is None:
                    continue
                for index, argument in enumerate(args):
                    if index >= len(target.params):
                        break
                    param = target.params[index]
                    if param in target.text_params:
                        continue
                    if param in getattr(target, "numeric_params", set()):
                        continue
                    if _argument_is_text(program, argument, scope):
                        target.text_params.add(param)
                        changed = True


def _validate_call_kinds(program: ParsedProgram) -> None:
    """Report argument/parameter kind mismatches at the call site."""
    entries = [(node, None) for node in _walk_all(program.top)]
    for function in program.functions.values():
        entries.extend((node, function) for node in _walk_all(function.body))
    for node, scope in entries:
        value = (node.value or "").strip()
        if not value:
            continue
        for call_name, args in _find_calls(value):
            target = program.functions.get(call_name)
            if target is None:
                continue
            for index, argument in enumerate(args):
                if index >= len(target.params):
                    break
                param = target.params[index]
                wants_text = param in getattr(target, "text_params", set())
                is_text = _argument_is_text(program, argument, scope)
                if wants_text and not is_text:
                    raise CompileError(
                        f"{node.source or program.path}:{node.line}: parameter "
                        f"{param!r} of {call_name!r} takes text, but this "
                        "argument is a number"
                    )
                if not wants_text and is_text and param not in getattr(
                    target, "numeric_params", set()
                ):
                    raise CompileError(
                        f"{node.source or program.path}:{node.line}: parameter "
                        f"{param!r} of {call_name!r} takes a number, but this "
                        "argument is text"
                    )


def _declared_kind(program, node, string_vars, bool_vars) -> str:
    """The kind a `set` value has, for annotation checking."""
    value = (node.value or "").strip()
    if not value:
        return "number"
    if value in ("true", "false"):
        return "bool"
    match = re.fullmatch(r"var\(([A-Za-z_][\w-]*)\)", value)
    if match is not None:
        name = match.group(1)
        if name in bool_vars:
            return "bool"
        if name in string_vars:
            return "text"
        return "number"
    if _has_compare(value):
        return "bool"
    if value.startswith('"') or len(split_amp(value)) > 1:
        return "text"
    if re.match(r"(?:upper|lower|chr|trim|char|mid|left|right)\s*\(", value):
        return "text"
    if _call_returns_text(program, value):
        return "text"
    return "number"


def _has_compare(value: str) -> bool:
    stripped = re.sub(r'"(?:[^"\\]|\\.)*"', '""', value)
    return re.search(r"(?<![<>=!])(?:<=|>=|!=|==|=|<|>)(?![=])", stripped) is not None


def _validate_declared_types(program, string_vars: set[str]) -> set[str]:
    """Check `set var(x): type = value` annotations and collect bool variables."""
    entries = [(node, None) for node in _walk_all(program.top)]
    for function in program.functions.values():
        entries.extend((node, function) for node in _walk_all(function.body))

    bool_vars: set[str] = set()
    for _pass in range(4):
        changed = False
        for node, _scope in entries:
            declared = getattr(node, "declared_type", None)
            if node.kind not in ("set", "local_set") or declared is None:
                continue
            kind = _declared_kind(program, node, string_vars, bool_vars)
            shown = {"number": "a number", "text": "text", "bool": "a bool"}[kind]
            if declared == "bool" and kind != "bool":
                raise CompileError(
                    f"{node.source or program.path}:{node.line}: declared bool "
                    f"but this value is {shown}; a bool is true, false or a "
                    "comparison"
                )
            if declared == "number" and kind != "number":
                raise CompileError(
                    f"{node.source or program.path}:{node.line}: declared number "
                    f"but this value is {shown}"
                )
            if declared == "text" and kind != "text":
                raise CompileError(
                    f"{node.source or program.path}:{node.line}: declared text "
                    f"but this value is {shown}"
                )
            if declared == "bool" and node.name not in bool_vars:
                bool_vars.add(node.name)
                changed = True
        if not changed:
            break
    return bool_vars


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
    for _ in range(6):
        _classify_string_variables(program, strict=False)
        changed = _classify_text_functions(
            program, _classify_string_variables(program, strict=False)
        )
        before = {
            name: set(getattr(fn, "text_params", set()))
            for name, fn in program.functions.items()
        }
        _classify_text_params(program)
        after = {
            name: set(getattr(fn, "text_params", set()))
            for name, fn in program.functions.items()
        }
        if not changed and before == after:
            break
    string_vars = _classify_string_variables(program, strict=True)
    _classify_text_functions(program, string_vars)
    _classify_text_params(program)
    _validate_call_kinds(program)
    program.bool_variables = _validate_declared_types(program, string_vars)
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
        for node in _walk_all(fn.body):
            value = node.value or ""
            for match in re.finditer(r"array\(\s*([A-Za-z_][\w-]*)\s*,", value):
                name = match.group(1)
                if name in program.arrays or name in fn.local_arrays:
                    continue
                raise CompileError(
                    f"{node.source or path}:{node.line}: unknown array {name!r}"
                )
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

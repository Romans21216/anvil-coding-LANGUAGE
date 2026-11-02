"""Type and lower opaque Anvil function references for both backends.

References have one numeric signature and cannot participate in arithmetic.
Only functions whose references are taken become dispatch candidates. Anvil
programs never receive raw addresses, dynamic symbol lookup, or an interpreter.
"""

from __future__ import annotations

import re

from compiler.common import IDENTIFIER, CompileError, Node
from compiler.expressions import split_args, validate_expression_depth
from compiler.lexer import mask_strings

PREFIX = "_anvil_callable"
REFERENCE = re.compile(rf"fnref\(\s*({IDENTIFIER})\s*\)")
STORAGE = re.compile(rf"\b(varl|var|local)\(\s*({IDENTIFIER})\s*\)")
DYNAMIC = re.compile(
    rf"\bcall\s+(varl|var|local)\(\s*({IDENTIFIER})(?=\s*[,\)])"
)
ASSIGNMENTS = ("set", "global_set", "local_set")


def lower_callables(program) -> None:
    """Replace function-reference assignments and calls with checked dispatch."""
    rows = []

    def collect(nodes, scope):
        pending = list(nodes)
        while pending:
            node = pending.pop()
            if node.kind != "metadata":
                rows.append((node, scope))
                pending.extend(node.body)
                pending.extend(node.otherwise)

    collect(program.top, None)
    for function in program.functions.values():
        collect(function.body, function)

    has_callback_use = any(
        node.kind in ("indirect_call", "callback_clear")
        or re.search(
            r"\bfnref\(|\bcall\s+(?:varl|var|local)\(",
            mask_strings(node.value + " " + " ".join(node.params)),
        )
        for node, _scope in rows
    )
    if not has_callback_use:
        return

    def error(node, message):
        raise CompileError(f"{node.source or program.path}:{node.line}: {message}")

    def storage_key(kind, name, scope):
        if kind == "local" or (
            kind == "var" and scope is not None and name in scope.params
        ):
            return "local", scope.name if scope else None, name
        return "global", name

    def assignment_key(node, scope):
        if node.kind.startswith("local_"):
            kind = "local"
        elif node.kind.startswith("global_"):
            kind = "varl"
        else:
            kind = "var"
        return storage_key(kind, node.name, scope)

    def target_reference(node):
        match = REFERENCE.fullmatch(node.value.strip())
        if not match:
            return None
        name = match[1]
        function = program.functions.get(name)
        if function is None:
            error(node, f"unknown function reference {name!r}")
        arity = len(function.params)
        if arity > 15:
            error(node, "function references support at most fifteen numeric arguments")
        return name, arity

    types = {}
    candidates = {}
    copies = []
    references = {}

    def merge(storage, arity, targets, node):
        if (
            storage[0] == "local"
            and len(storage) == 3
            and storage[1] in program.functions
            and storage[2] in program.functions[storage[1]].params
        ):
            error(
                node,
                "function-reference parameters are not supported; use a separate callback variable",
            )
        if storage in types and types[storage] != arity:
            error(node, "callback assignments must have the same argument count")
        types[storage] = arity
        known = candidates.setdefault(storage, set())
        previous_count = len(known)
        known.update(targets)
        return len(known) != previous_count

    for node, scope in rows:
        if node.kind not in ASSIGNMENTS:
            continue
        reference = target_reference(node)
        if reference:
            name, arity = reference
            merge(assignment_key(node, scope), arity, {name}, node)
            references[name] = 0
            continue
        copy = STORAGE.fullmatch(node.value.strip())
        if copy:
            copies.append((node, scope, storage_key(copy[1], copy[2], scope)))

    changed = True
    while changed:
        changed = False
        for node, scope, source in copies:
            if source in types:
                changed = (
                    merge(
                        assignment_key(node, scope),
                        types[source],
                        candidates[source],
                        node,
                    )
                    or changed
                )

    for identifier, name in enumerate(sorted(references), start=1):
        references[name] = identifier

    helpers = []

    def dispatch(kind, name, arguments, node, scope):
        storage = storage_key(kind, name, scope)
        if storage not in types:
            error(node, f"{kind}({name}) is not a declared function reference")
        arity = types[storage]
        if len(arguments) != arity:
            error(node, f"callback {name!r} expects {arity} argument(s), got {len(arguments)}")

        helper_name = f"{PREFIX}_dispatch_{len(helpers) + 1}"
        params = ["handle"] + [f"argument_{index}" for index in range(arity)]
        helper = Node("function", node.line, name=helper_name, params=params, source=node.source)
        helpers.append(helper)
        call_arguments = ", ".join(f"var({param})" for param in params[1:])

        for target in sorted(candidates[storage]):
            call = f"call fn({target}"
            if call_arguments:
                call += f", {call_arguments}"
            call += ")"
            helper.body.append(
                Node(
                    "if",
                    node.line,
                    value=f"var(handle) == {references[target]}",
                    source=node.source,
                    body=[Node("output", node.line, value=call, source=node.source)],
                )
            )

        helper.body.append(Node("callable_error", node.line, source=node.source))
        temp_names = [f"{helper_name}_arg_{index}" for index in range(arity + 1)]
        (scope if scope is not None else node).c_temporaries.update(temp_names)
        return helper_name, [f"{kind}({name})"] + arguments

    def transform(text, node, scope, *, allow_copy=False):
        validate_expression_depth(text, node.source or program.path, node.line)
        masked = mask_strings(text)
        dynamic_calls = list(DYNAMIC.finditer(masked))

        for match in STORAGE.finditer(masked):
            if storage_key(match[1], match[2], scope) not in types:
                continue
            if allow_copy and match.span() == (0, len(text)):
                continue
            if any(call.start(1) == match.start(1) for call in dynamic_calls):
                continue
            error(
                node,
                "function references cannot be used as numeric values; invoke them with call",
            )

        if re.search(r"\bfnref\(", masked):
            error(node, "fnref(function) must be assigned directly to a callback variable")

        result = []
        position = 0
        for match in dynamic_calls:
            if match.start() < position:
                continue
            opening = masked.index("(", match.start())
            end = opening + 1
            depth = 1
            while end < len(masked) and depth:
                depth += (masked[end] == "(") - (masked[end] == ")")
                end += 1
            if depth:
                error(node, "unclosed callback call")

            parts = split_args(text[opening + 1 : end - 1])
            arguments = [transform(part, node, scope) for part in parts[1:]]
            helper_name, call_arguments = dispatch(match[1], match[2], arguments, node, scope)
            result.append(text[position : match.start()])
            result.append(f"call fn({helper_name}, {', '.join(call_arguments)})")
            position = end

        result.append(text[position:])
        return "".join(result)

    for node, scope in rows:
        if node.kind == "callback_clear":
            storage = storage_key(node.params[0], node.name, scope)
            if storage in types:
                node.kind = (
                    "local_set"
                    if node.params[0] == "local"
                    else "global_set"
                    if node.params[0] == "varl"
                    else "set"
                )
                node.value = "0"
            elif node.params[0] == "var":
                # Version 1 cleanup syntax remains a no-op for numeric globals.
                node.kind = "noop"
            else:
                error(node, "null can only clear a function-reference variable")
            continue

        if node.kind == "for" and storage_key("local", node.name, scope) in types:
            error(node, "a function-reference variable cannot be a for-loop counter")

        if node.kind in ASSIGNMENTS and assignment_key(node, scope) in types:
            reference = target_reference(node)
            if reference:
                node.value = str(references[reference[0]])
            else:
                copy = STORAGE.fullmatch(node.value.strip())
                if not copy or storage_key(copy[1], copy[2], scope) not in types:
                    error(
                        node,
                        "callback variables may contain only fnref, another callback, or null",
                    )
                node.value = transform(node.value.strip(), node, scope, allow_copy=True)
        else:
            if (
                node.kind
                in ("add", "sub", "local_add", "local_sub", "global_add", "global_sub")
                and assignment_key(node, scope) in types
            ):
                error(node, "function references cannot be changed with add/sub")
            node.value = transform(node.value, node, scope)

        if node.kind == "indirect_call":
            kind = node.params[0]
            helper_name, arguments = dispatch(kind, node.name, split_args(node.value), node, scope)
            node.kind = "call"
            node.name = helper_name
            node.value = ", ".join(arguments)
            node.params = []
        else:
            node.params = [transform(value, node, scope) for value in node.params]

    program.functions.update((helper.name, helper) for helper in helpers)

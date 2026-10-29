"""Bounded include graph and source-owned binding for selective function imports."""

from collections import deque
from dataclasses import dataclass, field, replace
from pathlib import Path
import re

from compiler.common import (ArrayDeclarations, CompileError, ParsedProgram,
                             IDENTIFIER, FUNCTION_REFERENCE, c_name, function_reference)
from compiler.expressions import split_args, validate_expression_depth
from compiler.lexer import mask_strings

PRIVATE_PREFIX = "_anvil_include"
CALL = re.compile(rf'\bcall\s+fn\(\s*({FUNCTION_REFERENCE})(?=\s*[,\)])')
VARIABLE = re.compile(rf'\bvar\(({IDENTIFIER})\)')
ARRAY = re.compile(rf'\barray\(\s*({IDENTIFIER})(?=\s*,)')


@dataclass(eq=False)
class Scope:
    number: int
    functions: dict = field(default_factory=dict)
    variables: set = field(default_factory=set)
    arrays: ArrayDeclarations = field(default_factory=ArrayDeclarations)
    top: list = field(default_factory=list)
    variable_references: list = field(default_factory=list)
    local_references: list = field(default_factory=list)
    aliases: dict = field(default_factory=dict)
    needed: set = field(default_factory=set)

    def symbol(self, kind, name):
        return f"{PRIVATE_PREFIX}_{self.number}_{kind}_{name}" if self.number else name


def clone_node(node):
    """Clone without Python recursion, including untrusted deeply nested syntax."""
    def shell(old):
        return replace(old, params=list(old.params), locals=set(old.locals),
                       local_arrays=dict(old.local_arrays),
                       local_array_lines=dict(old.local_array_lines), body=[], otherwise=[])
    result = shell(node)
    pending = [(node,result)]
    while pending:
        old,new = pending.pop()
        for attribute in ("body","otherwise"):
            for child in getattr(old,attribute):
                copied = shell(child)
                getattr(new,attribute).append(copied)
                pending.append((child,copied))
    return result


class ProgramLoader:
    def __init__(self, path, root):
        self.path = Path(path)
        self.root = Path(root).resolve() if root is not None else self.path.resolve().parent
        self.flat = Scope(0)
        self.scopes = [self.flat]
        self.modules = {}
        self.cache = {}
        self.seen = set()
        self.active = []
        self.source_bytes = self.expanded_bytes = 0
        self.order = []
        self.queue = deque()
        self.bound = {}

    def error(self, node, message):
        raise CompileError(f"{node.source or self.path}:{node.line}: {message}")

    def read(self, path, text, where):
        from compiler import modules as limits
        from compiler.parser import parse_syntax
        canonical = path.resolve()
        if canonical in self.cache:
            return self.cache[canonical]
        if text is None:
            try:
                with canonical.open("rb") as stream:
                    payload = stream.read(limits.MAX_SOURCE_BYTES-self.source_bytes+1)
                if len(payload)+self.source_bytes > limits.MAX_SOURCE_BYTES:
                    raise CompileError(f"{where}: include source exceeds the 4 MiB budget")
                text = payload.decode("utf-8-sig")
                size = len(payload)
            except (OSError,UnicodeError) as error:
                raise CompileError(f"{where}: cannot read include {canonical}: {error}") from error
        else:
            size = len(text.encode("utf-8"))
        self.source_bytes += size
        if self.source_bytes > limits.MAX_SOURCE_BYTES:
            raise CompileError(f"{where}: include source exceeds the 4 MiB budget")
        unit = parse_syntax(path,text)
        # Compiler-owned identities cannot alias source symbols after C sanitizing.
        sites = [(name,fn.line) for name,fn in unit.functions.items()]
        sites += [(name,unit.arrays.locations[name][1]) for name in unit.arrays]
        sites += [(name,line) for name,line,_,_ in unit.variable_references]
        for fn in unit.functions.values():
            sites += [(name,fn.line) for name in fn.params+list(fn.locals)+list(fn.local_arrays)]
        for name,line in sites:
            if c_name(name).startswith(c_name(PRIVATE_PREFIX)):
                raise CompileError(f"{path}:{line}: identifier prefix {PRIVATE_PREFIX} is reserved for include identities")
        self.cache[canonical] = unit,size
        return unit,size

    def visit(self, scope, path, text=None, origin=None):
        from compiler import modules as limits
        canonical = path.resolve()
        where = f"{origin.source}:{origin.line}" if origin else str(path)
        if canonical in self.active:
            chain = " -> ".join(map(str,self.active+[canonical]))
            raise CompileError(f"{where}: include cycle: {chain}")
        key = scope.number,canonical
        if key in self.seen:
            return
        if len(self.active) >= limits.MAX_INCLUDE_DEPTH:
            raise CompileError(f"{where}: include nesting exceeds {limits.MAX_INCLUDE_DEPTH} files")
        if len(self.seen) >= limits.MAX_INCLUDE_FILES:
            raise CompileError(f"{where}: include graph exceeds {limits.MAX_INCLUDE_FILES} file instances")
        unit,size = self.read(path,text,where)
        self.expanded_bytes += size
        if self.expanded_bytes > limits.MAX_SOURCE_BYTES:
            raise CompileError(f"{where}: expanded include source exceeds the 4 MiB budget")
        self.seen.add(key)
        self.active.append(canonical)
        for name,fn in unit.functions.items():
            if name in scope.functions:
                previous = scope.functions[name]
                self.error(fn,f"duplicate function {name!r}; already declared at {previous.source}:{previous.line}")
            scope.functions[name] = fn
        for name,size in unit.arrays.items():
            if name in scope.arrays:
                previous,line = scope.arrays.locations[name]
                raise CompileError(f"{path}:{unit.arrays.locations[name][1]}: duplicate array {name!r}; already declared at {previous}:{line}")
            scope.arrays[name] = size
            scope.arrays.locations[name] = unit.arrays.locations[name]
        scope.variables.update(unit.variables)
        scope.variable_references.extend(unit.variable_references)
        scope.local_references.extend(unit.local_references)
        for node in unit.top:
            if node.kind != "include":
                if scope.number and node.kind not in ("set","add","sub","call","seed"):
                    self.error(node,"selective include requires a library; use a whole-file include for engine configuration")
                scope.top.append(node)
                self.order.append((scope,node))
                continue
            relative = limits.include_name(node.value,path,node.line)
            target = (canonical.parent/relative).resolve()
            try:
                target.relative_to(self.root)
            except ValueError as error:
                raise CompileError(f"{path}:{node.line}: include must resolve inside {self.root}") from error
            if not node.name:
                self.visit(scope,target,origin=node)
                continue
            if target not in self.modules:
                module = Scope(len(self.scopes))
                self.scopes.append(module)
                self.modules[target] = module
            module = self.modules[target]
            self.visit(module,target,origin=node)
            if node.name not in module.functions:
                self.error(node,f"included file does not define function {node.name!r}")
            alias = node.params[0]
            alias_key = canonical,alias
            previous = scope.aliases.get(alias_key)
            if previous is not None and previous[0] is not module:
                self.error(node,f"module qualifier {alias!r} names different files; use 'as alias'")
            if previous is None:
                scope.aliases[alias_key] = module,set()
            scope.aliases[alias_key][1].add(node.name)
            self.require(module,node.name)
        self.active.pop()

    def require(self, scope, name):
        if name not in scope.needed:
            scope.needed.add(name)
            self.queue.append((scope,name))

    def resolve(self, reference, scope, node, count=None):
        name,alias = function_reference(reference,node.source or self.path,node.line)
        target = scope
        if alias:
            imported = scope.aliases.get(((node.source or self.path).resolve(),alias))
            if imported is None:
                self.error(node,f"unknown module qualifier {alias!r}; add a selective include")
            target,exports = imported
            if name not in exports:
                self.error(node,f"function {name!r} was not included from {alias!r}")
        if alias or scope.number:
            if name not in target.functions:
                self.error(node,f"unknown function {name!r} in included module")
            expected = len(target.functions[name].params)
            if count is not None and count != expected:
                self.error(node,f"function {reference!r} expects {expected} argument(s), got {count}")
            self.require(target,name)
        return target.symbol("f",name)

    def rewrite(self, text, scope, fn, node):
        masked = mask_strings(text)
        edits = []
        for match in CALL.finditer(masked):
            if not scope.number and match[3] is None:
                continue  # preserve legacy unqualified validation/emission timing
            validate_expression_depth(text,node.source or self.path,node.line)
            depth = 1
            # The match stops before the argument comma or closing parenthesis.
            # Walk from fn( so nested argument calls cannot alter this arity.
            opening = masked.index("(",match.start())
            end = opening+1
            while end < len(masked) and depth:
                depth += (masked[end] == "(")-(masked[end] == ")")
                end += 1
            count = None if depth else len(split_args(text[opening+1:end-1]))-1
            edits.append((match.start(1),match.end(1),self.resolve(match[1],scope,node,count)))
        if scope.number:
            for match in VARIABLE.finditer(masked):
                name = match[1]
                if fn is None or name not in fn.params:
                    edits.append((match.start(1),match.end(1),scope.symbol("v",name)))
            for match in ARRAY.finditer(masked):
                name = match[1]
                if fn is not None and name in fn.local_arrays:
                    continue
                if name not in scope.arrays:
                    self.error(node,f"unknown array {name!r} in included module")
                edits.append((match.start(1),match.end(1),scope.symbol("a",name)))
        for start,end,value in sorted(edits,reverse=True):
            text = text[:start]+value+text[end:]
        return text

    def bind(self, original, scope, fn=None):
        result = clone_node(original)
        pending = [result]
        while pending:
            node = pending.pop()
            if node.kind == "call":
                node.name = self.resolve(node.name,scope,node,len(split_args(node.value)))
            elif scope.number and node.kind in ("set","add","sub"):
                if fn is None or node.name not in fn.params:
                    node.name = scope.symbol("v",node.name)
            elif scope.number and node.kind == "array_set":
                if fn is None or node.name not in fn.local_arrays:
                    if node.name not in scope.arrays:
                        self.error(node,f"unknown array {node.name!r} in included module")
                    node.name = scope.symbol("a",node.name)
            node.value = self.rewrite(node.value,scope,fn,node)
            node.params = [self.rewrite(value,scope,fn,node) for value in node.params]
            pending.extend(node.body)
            pending.extend(node.otherwise)
        return result

    def load(self, source):
        from compiler.semantics import validate_program
        self.visit(self.flat,self.path,source)
        for name in self.flat.functions:
            self.require(self.flat,name)
        top = [self.bind(node,scope) for scope,node in self.order]
        while self.queue:
            scope,name = self.queue.popleft()
            original = scope.functions[name]
            function = self.bind(original,scope,original)
            function.name = scope.symbol("f",name)
            function.original_name = name if scope.number else original.original_name
            self.bound[scope,name] = function
        result = ParsedProgram(self.path,{},top,set(),ArrayDeclarations(),[],[])
        for scope in self.scopes:
            kept = {name:fn for name,fn in scope.functions.items() if name in scope.needed}
            var_refs = [ref for ref in scope.variable_references if ref[2] is None or ref[2] in kept]
            local_refs = [ref for ref in scope.local_references if ref[2] in kept]
            # Validate with original source names before introducing private IDs.
            if kept:
                validate_program(ParsedProgram(self.path,kept,scope.top,scope.variables,
                                               scope.arrays,var_refs,local_refs),check_symbols=not scope.number)
            for name in kept:
                result.functions[scope.symbol("f",name)] = self.bound[scope,name]
            result.variables.update(scope.symbol("v",name) for name in scope.variables)
            for name,size in scope.arrays.items():
                key = scope.symbol("a",name)
                result.arrays[key] = size
                result.arrays.locations[key] = scope.arrays.locations[name]
            for name,line,owner,path in var_refs:
                fn = scope.functions.get(owner)
                bound = name if fn is not None and name in fn.params else scope.symbol("v",name)
                result.variable_references.append((bound,line,scope.symbol("f",owner) if owner else None,path))
            result.local_references.extend((name,line,scope.symbol("f",owner),path)
                                           for name,line,owner,path in local_refs)
        return result

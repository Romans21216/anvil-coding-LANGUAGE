#!/usr/bin/env python3
"""Compatibility facade and command-line entry point for the Anvil compiler."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler.build import build_c, find_compiler
from compiler.cli import main
from compiler.codegen import (
    emit_c,
    emit_display,
    emit_nodes,
    local_array_cleanup,
    rgb_style,
)
from compiler.common import (
    INCLUDE,
    LANGUAGE_VERSION,
    MAX_ACTIVE_LOCAL_ARRAY_BYTES,
    MAX_ARRAY_SIZE,
    MAX_LOCAL_ARRAY_ELEMENTS,
    ROOT as PROJECT_ROOT,
    RUNTIME,
    RUNTIME_C_NAMES,
    CompileError,
    Node,
    array_code,
    array_size,
    c_name,
    variable_code,
)
from compiler.expressions import (
    BUILTINS,
    BUILTIN_C_NAMES,
    BUILTIN_STRING_ARGUMENTS,
    TOKEN,
    ExpressionParser,
    expr,
    split_args,
)
from compiler.lexer import split_keyword, strip_comment, validate_port
from compiler.parser import parse, parse_syntax
from compiler.semantics import validate_program

__all__ = [
    "CompileError",
    "Node",
    "ExpressionParser",
    "parse",
    "parse_syntax",
    "validate_program",
    "emit_c",
    "emit_display",
    "emit_nodes",
    "rgb_style",
    "local_array_cleanup",
    "expr",
    "split_args",
    "find_compiler",
    "build_c",
    "main",
    "c_name",
    "variable_code",
    "array_size",
    "array_code",
    "strip_comment",
    "validate_port",
    "split_keyword",
    "ROOT",
    "PROJECT_ROOT",
    "RUNTIME",
    "INCLUDE",
    "RUNTIME_C_NAMES",
    "MAX_ARRAY_SIZE",
    "MAX_LOCAL_ARRAY_ELEMENTS",
    "MAX_ACTIVE_LOCAL_ARRAY_BYTES",
    "LANGUAGE_VERSION",
    "TOKEN",
    "BUILTINS",
    "BUILTIN_C_NAMES",
    "BUILTIN_STRING_ARGUMENTS",
]

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Differential probe: run the same programs on both backends and diff output."""

from __future__ import annotations

import contextlib
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402
from compiler.parser import parse  # noqa: E402


def prog(*lines: str) -> str:
    body = "\n".join("  " + line for line in lines)
    return f"fn(main)\n{body}\nend\ncall fn(main)\n"


LONG200 = "x" * 200
ZEDS200 = "z" * 200

CASES: dict[str, str] = {
    # battery 1: text edges
    "left_empty": 'fn(main)\n  say "[" & left("", 3) & "]"\n  say "[" & left("abc", 0) & "]"\nend\ncall fn(main)\n',
    "right_empty": 'fn(main)\n  say "[" & right("", 5) & "]"\n  say "[" & right("abc", 0) & "]"\nend\ncall fn(main)\n',
    "right_negative": 'fn(main)\n  say "[" & right("abcdef", -1) & "]"\n  say "[" & right("abcdef", 6) & "]"\n  say "[" & right("abcdef", 7) & "]"\nend\ncall fn(main)\n',
    "left_exact": 'fn(main)\n  say left("abcdef", 6)\n  say left("abcdef", 7)\nend\ncall fn(main)\n',
    "mid_edges": 'fn(main)\n  say "[" & mid("abcdef", 0, 0) & "]"\n  say "[" & mid("abcdef", 6, 2) & "]"\n  say "[" & mid("abcdef", 5, 10) & "]"\nend\ncall fn(main)\n',
    "char_edges": 'fn(main)\n  say "[" & char("abc", 3) & "]"\n  say "[" & char("abc", -1) & "]"\nend\ncall fn(main)\n',
    "mod_edges": 'fn(main)\n  say 0 % 5\n  say 5 % 5\n  say -5 % 5\n  say 5.5 % 2.5\n  say 1 % 0.5\nend\ncall fn(main)\n',
    "mod_zero": 'fn(main)\n  say 1 % 0\nend\ncall fn(main)\n',
    "text_compare_edges": 'fn(main)\n  say "a" < "ab"\n  say "ab" > "a"\n  say "a" = "a"\n  say "" < "a"\n  say "Z" < "a"\nend\ncall fn(main)\n',
    "join_number_render": 'fn(main)\n  say 1 / 4\n  say "n=" & 0.1\n  say 10 / 4\nend\ncall fn(main)\n',
    "len_utf8": 'fn(main)\n  say len("caf\u00e9")\n  say upper("caf\u00e9")\nend\ncall fn(main)\n',
    "trim_tabs": 'fn(main)\n  set var(w) = "  \\t x \\t  "\n  say "[" & trim(var(w)) & "]"\nend\ncall fn(main)\n',
    "number_edges": 'fn(main)\n  say number("")\n  say number("abc")\n  say number("-3.5")\n  say number("  7 ")\nend\ncall fn(main)\n',
    "chr_edges": 'fn(main)\n  say chr(0)\n  say chr(255)\n  say ord("")\nend\ncall fn(main)\n',
    "text_fn_join": 'fn(tag)\n  output "x" & "y"\nend\nfn(main)\n  say "[" & call fn(tag) & "]"\n  say len(call fn(tag))\nend\ncall fn(main)\n',
    "repeat_zero": 'fn(main)\n  repeat 0\n    say "never"\n  end\n  repeat -3\n    say "never"\n  end\n  say "done"\nend\ncall fn(main)\n',
    "for_desc": 'fn(main)\n  for local(i) = 3 to 1\n    say local(i)\n  end\n  say "after"\nend\ncall fn(main)\n',
    "while_text": 'fn(main)\n  set var(s) = "ab"\n  while len(var(s)) > 0\n    say var(s)\n    set var(s) = left(var(s), len(var(s)) - 1)\n  end\nend\ncall fn(main)\n',
    "array_bounds_message": 'array a(2)\nfn(main)\n  say array(a, 5)\nend\ncall fn(main)\n',
    "nested_calls": 'fn(main)\n  say len(upper(trim("  ab  ")))\n  say left(right("abcdef", 4), 2)\nend\ncall fn(main)\n',
    "say_multi": 'fn(main)\n  say "a", 1, "b"\n  write "c"\n  write "d"\n  say ""\nend\ncall fn(main)\n',
    "concat_text_vars": 'fn(main)\n  set var(a) = "x"\n  set var(b) = var(a) & var(a)\n  say var(b)\n  set var(a) = var(b) & "z"\n  say var(a)\nend\ncall fn(main)\n',
    "asks": 'fn(main)\n  set var(n) = 0\n  ask "n? ", var(n)\n  say var(n) * 2\nend\ncall fn(main)\n',
    "empty_say": 'fn(main)\n  say ""\n  say "x"\nend\ncall fn(main)\n',
    # battery 2: syntax and edges
    "escapes": 'fn(main)\n  say "a\\nb"\n  say "tab\\there"\n  say "q\\"q"\n  say "back\\\\slash"\nend\ncall fn(main)\n',
    "nested_text": 'fn(main)\n  say len(left(right(upper("  hi  "), 2), 1))\n  say trim(upper("  ab  "))\nend\ncall fn(main)\n',
    "ord_chr_roundtrip": 'fn(main)\n  say ord(chr(66))\n  say ord("hello")\nend\ncall fn(main)\n',
    "chr_range_high": 'fn(main)\n  say chr(256)\nend\ncall fn(main)\n',
    "chr_range_low": 'fn(main)\n  say chr(-1)\nend\ncall fn(main)\n',
    "array_fraction_index": 'array a(3)\nfn(main)\n  set array(a, 1.7) = 9\n  say array(a, 1)\nend\ncall fn(main)\n',
    "array_negative_index": 'array a(3)\nfn(main)\n  say array(a, -1)\nend\ncall fn(main)\n',
    "for_negative_step": 'fn(main)\n  for local(i) = 5 to 1 step -2\n    say local(i)\n  end\n  say "done"\nend\ncall fn(main)\n',
    "while_false_start": 'fn(main)\n  while 0 > 1\n    say "never"\n  end\n  say "after"\nend\ncall fn(main)\n',
    "say_parts": 'fn(main)\n  say "x", 1 + 1, "y"\n  say 3, 4\nend\ncall fn(main)\n',
    "recursion": 'fn(fact, n)\n  if var(n) <= 1\n    output 1\n  end\n  output var(n) * call fn(fact, var(n) - 1)\nend\nfn(main)\n  say call fn(fact, 5)\nend\ncall fn(main)\n',
    "many_params": 'fn(sum8, a, b, c, d, e, f, g, h)\n  output var(a) + var(b) + var(c) + var(d) + var(e) + var(f) + var(g) + var(h)\nend\nfn(main)\n  say call fn(sum8, 1, 2, 3, 4, 5, 6, 7, 8)\nend\ncall fn(main)\n',
    "divide_zero": 'fn(main)\n  say 1 / 0\nend\ncall fn(main)\n',
    "big_numbers": 'fn(main)\n  say 10000000000\n  say 0.000001\n  say 123456789.5\nend\ncall fn(main)\n',
    "number_exponent": 'fn(main)\n  say number("1e3")\n  say number("+5")\n  say number(".5")\nend\ncall fn(main)\n',
    "mid_fractional": 'fn(main)\n  say "[" & mid("abcdef", 1.9, 2.9) & "]"\n  say "[" & left("abcdef", 2.9) & "]"\n  say "[" & right("abcdef", 2.9) & "]"\nend\ncall fn(main)\n',
    "ask_negative": 'fn(main)\n  set var(n) = 0\n  ask "n? ", var(n)\n  say var(n)\nend\ncall fn(main)\n',
    # battery 3: long text and loops
    "long_literal": prog(f'say "{LONG200}"'),
    "join_over_cap": prog(
        f'set var(a) = "{LONG200}"',
        "set var(b) = var(a) & var(a)",
        "say len(var(b))",
    ),
    "text_edge_200": prog(
        f'set var(w) = "{ZEDS200}"',
        "say len(left(var(w), 199))",
        "say len(right(var(w), 5))",
        "say len(mid(var(w), 100, 50))",
    ),
    "loop_with_stop": prog(
        "set var(i) = 0",
        "while var(i) < 10",
        "  add var(i) 1",
        "  if var(i) = 3",
        "    stop",
        "  end",
        "end",
        "say var(i)",
    ),
    "and_or_chain": prog(
        'set var(a) = 1',
        'set var(b) = 0',
        "if var(a) = 1 and var(b) = 0",
        '  say "both"',
        "end",
        "if var(a) = 9 or var(b) = 0",
        '  say "either"',
        "end",
    ),
    "local_array_sum": 'array g(2)\nfn(sum2, a, b)\n  output var(a) + var(b)\nend\nfn(main)\n  set array(g, 0) = 1\n  set array(g, 1) = 2\n  say call fn(sum2, array(g, 0), array(g, 1))\nend\ncall fn(main)\n',
    # battery 4: text builtin edges, fractional loops, control flow
    "contains_edges": prog(
        'say contains("", "")',
        'say contains("", "a")',
        'say contains("abc", "")',
        'say starts_with("", "")',
        'say ends_with("", "")',
        'say starts_with("abc", "abcd")',
    ),
    "trim_all_ws": prog(
        'set var(a) = "   "',
        'set var(b) = "\\t\\t"',
        'set var(c) = "a\\tb"',
        'say "[" & trim(var(a)) & "]"',
        'say "[" & trim(var(b)) & "]"',
        'say "[" & trim(var(c)) & "]"',
    ),
    "case_edges": prog(
        'say "[" & upper("") & "]"',
        'say "[" & lower("") & "]"',
        'say upper("MiXeD 123")',
        'say lower("MiXeD 123")',
    ),
    "empty_text_builtins": prog(
        'say "[" & char("", 0) & "]"',
        'say "[" & mid("", 0, 1) & "]"',
        'say "[" & left("", 0) & "]"',
        'say "[" & right("", 0) & "]"',
    ),
    "repeat_fractional": prog(
        "repeat 2.9",
        '  say "r"',
        "end",
        "repeat 0.5",
        '  say "never"',
        "end",
        'say "done"',
    ),
    "for_fractional": prog(
        "for local(i) = 0 to 1 step 0.5",
        "  say local(i)",
        "end",
        'say "done"',
    ),
    "say_and_or": prog(
        "say 1 and 1",
        "say 1 or 0",
        "say 0 and 1",
        "say 2 and 3",
    ),
    "stop_in_function": 'fn(quit)\n  stop\nend\nfn(main)\n  say 1\n  call fn(quit)\n  say 2\nend\ncall fn(main)\n',
    "wait_zero": prog('wait 0', 'say "ok"'),
    "join_then_compare": prog(
        'if "a" & "b" = "ab"',
        '  say "joined-equal"',
        "else",
        '  say "different"',
        "end",
    ),
    "len_after_join": prog(
        'set var(a) = "abc"',
        'set var(b) = var(a) & "de"',
        "say len(var(b))",
    ),
    # battery 5: deeper nesting, stack args, index expressions
    "join_fraction": prog(
        'say "third=" & 1 / 3',
        'say "big=" & 10000000000',
    ),
    "many_arg_call": (
        "fn(sum12, a, b, c, d, e, f, g, h, i, j, k, l)\n"
        "  output var(a) + var(b) + var(c) + var(d) + var(e) + var(f) + var(g) + var(h) + var(i) + var(j) + var(k) + var(l)\n"
        "end\nfn(main)\n  say call fn(sum12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)\n"
        "end\ncall fn(main)\n"
    ),
    "deep_recursion": (
        "fn(down, n)\n  if var(n) <= 0\n    output 0\n  end\n"
        "  output 1 + call fn(down, var(n) - 1)\nend\n"
        "fn(main)\n  say call fn(down, 100)\nend\ncall fn(main)\n"
    ),
    "elif_chain": prog(
        "set var(n) = 7",
        "if var(n) = 1",
        '  say "one"',
        "elif var(n) = 2",
        '  say "two"',
        "elif var(n) = 7",
        '  say "seven"',
        "else",
        '  say "other"',
        "end",
    ),
    "array_index_expression": 'array a(4)\nfn(main)\n  set var(i) = 1\n  set array(a, var(i) + 1) = 42\n  say array(a, 2)\n  say array(a, var(i) + 1)\nend\ncall fn(main)\n',
    "nested_repeat": prog(
        "repeat 2",
        "  repeat 3",
        '    say "x"',
        "  end",
        "end",
    ),
    "stop_in_repeat": prog(
        "repeat 5",
        "  say 1",
        "  stop",
        "end",
        'say "never"',
    ),
    "while_and_or": prog(
        "set var(i) = 0",
        "while var(i) < 3 and var(i) >= 0",
        "  add var(i) 1",
        "end",
        "say var(i)",
    ),
    "long_text_compare": (
        f"fn(main)\n  set var(a) = \"{ZEDS200}\"\n"
        f"  set var(b) = \"{ZEDS200}\"\n"
        "  say var(a) = var(b)\n"
        '  say var(a) < "zzz"\n'
        "end\ncall fn(main)\n"
    ),
    "utf8_join": prog(
        'set var(w) = "caf\u00e9"',
        'say var(w) & "!"',
        "say len(var(w))",
    ),
    # battery 6: number() oddities, text edge cases, control flow
    "number_oddities": prog(
        'say number("0x10")',
        'say number("1_000")',
        'say number("  -0.0  ")',
        'say number("12abc")',
    ),
    "number_inf": prog('say number("inf")'),
    "trim_newlines": prog(
        'set var(w) = "\\n x \\n"',
        'say "[" & trim(var(w)) & "]"',
    ),
    "contains_overlap": prog(
        'say contains("aaaa", "aa")',
        'say contains("abcabc", "cab")',
        'say contains("abc", "abcd")',
    ),
    "say_ten_parts": prog(
        'say "a", 1, "b", 2, "c", 3, "d", 4, "e", 5',
    ),
    "write_then_say": prog(
        'write "x"',
        'write 1',
        'say "y"',
    ),
    "stop_at_top": 'fn(main)\n  say 1\nend\nstop\ncall fn(main)\n',
    "for_step_zero": prog(
        "set var(n) = 0",
        "for local(i) = 0 to 5 step 0",
        "  add var(n) 1",
        "  if var(n) > 3",
        "    stop",
        "  end",
        "end",
        "say var(n)",
    ),
    "not_with_text": prog(
        'set var(s) = "yes"',
        'if not var(s) = "no"',
        '  say "not-no"',
        "end",
    ),
    "text_fn_in_if": (
        'fn(kind)\n  output "big"\nend\n'
        'fn(main)\n  if call fn(kind) = "big"\n    say "matched"\n  end\n'
        "end\ncall fn(main)\n"
    ),
    # battery 7: growable lists
    "list_basic": (
        "list nums\nfn(main)\n  add nums 5\n  add nums 7\n  say count(nums)\n"
        "  say array(nums, 0)\n  say array(nums, 1)\nend\ncall fn(main)\n"
    ),
    "list_empty": "list items\nfn(main)\n  say count(items)\nend\ncall fn(main)\n",
    "list_in_function": (
        "list words\nfn(fill)\n  add words 1\n  add words 2\nend\n"
        "fn(main)\n  call fn(fill)\n  say count(words)\n  say array(words, 1)\n"
        "end\ncall fn(main)\n"
    ),
    "list_join": (
        "list nums\nfn(main)\n  add nums 3\n  add nums 4\n"
        '  say "n=" & count(nums)\n  say "first=" & array(nums, 0)\n'
        "end\ncall fn(main)\n"
    ),
    "list_loop_sum": (
        "list nums\nfn(main)\n  for local(i) = 1 to 4\n    add nums local(i) * 10\n"
        "  end\n  set var(total) = 0\n"
        "  for local(i) = 0 to count(nums) - 1\n"
        "    add var(total) array(nums, local(i))\n  end\n"
        '  say "total=" & var(total)\nend\ncall fn(main)\n'
    ),
    "list_overflow": (
        "list nums\nfn(main)\n  for local(i) = 1 to 257\n    add nums local(i)\n"
        "  end\n  say count(nums)\nend\ncall fn(main)\n"
    ),
    "text_overflow_assign": prog(
        'set var(w) = "' + "a" * 300 + '"',
        "say len(var(w))",
    ),
    "text_overflow_join": prog(
        'say "x" & "' + "b" * 300 + '"',
    ),
    "multi_ask_numbers": (
        "fn(main)\n  set var(a) = 0\n  set var(b) = 0\n  set var(c) = 0\n"
        '  ask "1? ", var(a)\n  ask "2? ", var(b)\n  ask "3? ", var(c)\n'
        "  say var(a) + var(b) + var(c)\nend\ncall fn(main)\n",
        b"1\n2\n3\n",
    ),
    "multi_ask_text": (
        'fn(main)\n  set var(first) = ""\n  set var(last) = ""\n'
        '  ask "first? ", var(first)\n  ask "last? ", var(last)\n'
        '  say var(last) & ", " & var(first)\nend\ncall fn(main)\n',
        b"Ada\nLovelace\n",
    ),
    "ask_then_number": (
        "fn(main)\n  set var(n) = 0\n  set var(s) = \"\"\n"
        '  ask "n? ", var(n)\n  ask "s? ", var(s)\n'
        '  say var(s) & "=" & var(n)\nend\ncall fn(main)\n',
        b"7\nseven\n",
    ),
    "local_array_loop": (
        "fn(fill, n)\n  array slots(3)\n  for local(i) = 0 to 2\n"
        "    set array(slots, local(i)) = var(n) + local(i)\n  end\n"
        "  output array(slots, 0) + array(slots, 2)\nend\n"
        "fn(main)\n  say call fn(fill, 1)\n  say call fn(fill, 5)\nend\ncall fn(main)\n",
    ),
    "local_array_recursion": (
        "fn(depth, n)\n  array box(2)\n  set array(box, 0) = var(n)\n"
        "  if var(n) <= 0\n    output array(box, 0)\n  end\n"
        "  set array(box, 1) = call fn(depth, var(n) - 1)\n"
        "  output array(box, 0) + array(box, 1)\nend\n"
        "fn(main)\n  say call fn(depth, 3)\nend\ncall fn(main)\n",
    ),
    "local_array_bounds": (
        "fn(bad)\n  array tiny(2)\n  set array(tiny, 5) = 1\nend\n"
        "fn(main)\n  call fn(bad)\nend\ncall fn(main)\n",
    ),
    "negative_zero": "fn(main)\n  say 0 * -1\n  say -0.0000001\n"
    "  say \"x=\" & (0 * -1)\n  say -0.5\n  say -0.0000006\nend\ncall fn(main)\n",
    "text_bytes": (
        "fn(main)\n  say len(\"héllo\")\n  say upper(\"héllo\")\n"
        "  say char(\"héllo\", 1)\n  say chr(233)\n  say ord(\"é\")\n"
        "  say len(trim(\"  hé  \"))\nend\ncall fn(main)\n"
    ),
    "toplevel_set": (
        "set var(base) = 10\nset var(total) = var(base) * 2 + 1\n"
        'set var(label) = "total="\nseed(3)\n\n'
        "fn(bump)\n  set var(total) = var(total) + 1\nend\n\n"
        "fn(main)\n  say var(label) & var(total)\n  call fn(bump)\n"
        "  say var(total)\n  say rnd(1, 100)\nend\ncall fn(main)\n",
    ),
    "implicit_main_say": "set var(x) = 5\n\nfn(main)\n  say var(x) * 2\nend\n",
    "implicit_main_return": "fn(main)\n  output 1 / 3\nend\n",
    "two_top_level_calls": (
        'fn(first)\n  say "a"\nend\n\nfn(second)\n  say "b"\nend\n\n'
        "call fn(first)\ncall fn(second)\n"
    ),
    "text_order_edges": (
        "fn(main)\n  if \"abc\" < \"abd\"\n    say 1\n  end\n"
        '  if "ab" < "abc"\n    say 2\n  end\n'
        '  if "Z" < "a"\n    say 3\n  end\n'
        '  if "" < "a"\n    say 4\n  end\n'
        '  if "abc" >= "abc"\n    say 5\n  end\nend\ncall fn(main)\n'
    ),
    "join_builtins": (
        'fn(main)\n  set var(a) = "Hello"\n  set var(b) = "World"\n'
        "  set var(s) = upper(var(a)) & lower(var(b))\n  say var(s)\n"
        "  set var(n) = 1 & 2\n  say var(n)\n"
        '  set var(t) = trim(var(s)) & "!"\n  say var(t)\nend\ncall fn(main)\n'
    ),
    "join_len_and_six": (
        'fn(main)\n  say len("a" & "b")\n'
        '  say upper("a") & upper("b") & upper("c") & upper("d")'
        ' & upper("e") & upper("f")\n'
        '  say len(upper("a") & upper("b"))\nend\ncall fn(main)\n'
    ),
    "literals_with_syntax": (
        'fn(main)\n  say "a=b"\n  say "a & b"\n  say "a,b"\n'
        '  say "a # b"\n  say "end"\n  say "1+2"\n'
        '  set var(s) = "x # y"\n  say var(s)\n'
        '  say "if x > 1"\nend\ncall fn(main)\n'
    ),
    "short_circuit": (
        "set var(hits) = 0\n\nfn(bump)\n  set var(hits) = var(hits) + 1\n"
        "  output 1\nend\n\nfn(main)\n  say 1 < 2 and 2 < 3\n"
        "  say not 1 < 2\n  if 0 and call fn(bump) = 1\n    say 99\n  end\n"
        "  say var(hits)\n  if 1 or call fn(bump) = 1\n    say 7\n  end\n"
        "  say var(hits)\n  if 1 and call fn(bump) = 1\n    say 8\n  end\n"
        "  say var(hits)\nend\ncall fn(main)\n"
    ),
    "integration_program": (
        'list words\narray scores(3)\n\nfn(label, n)\n  if var(n) > 2\n    output "big"\n  end\n  output "small"\nend\n\nfn(total_of, count)\n  set local(sum) = 0\n  for local(i) = 1 to var(count)\n    add local(sum) local(i)\n  end\n  output local(sum)\nend\n\nfn(main)\n  add words 10\n  add words 20\n  set array(scores, 0) = 7\n  set array(scores, 2) = 9\n  say "words=" & count(words)\n  say "second=" & array(words, 1)\n  say "scores=" & (array(scores, 0) + array(scores, 2))\n  say "total=" & call fn(total_of, 4)\n  say "label=" & call fn(label, 5) & "/" & call fn(label, 1)\n  set var(name) = "  Ada  "\n  say "[" & trim(var(name)) & "] len=" & len(trim(var(name)))\n  say upper(var(name)) & "|" & lower(trim(var(name)))\n  if contains(var(name), "Ada") and starts_with(trim(var(name)), "A")\n    say "match"\n  end\n  say mid("abcdef", 2, 3) & right("abcdef", 2)\n  say number("12.5") * 2\n  say round(2.5) & "," & floor(2.9) & "," & ceil(2.1)\n  say 7 % 4 & " " & (1 / 4)\nend\ncall fn(main)\n',
    ),
}


def run(text: str, backend: str, stdin: bytes = bytes([10])) -> tuple[int, str, str]:
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        source = temp_path / "probe.ANVL"
        source.write_text(text, encoding="utf-8")
        try:
            functions, top, variables, arrays = parse(source, text)
            exe = temp_path / "probe.exe"
            with contextlib.redirect_stdout(open(os.devnull, "w")):
                if backend == "native":
                    exe.write_bytes(
                        NativeCodegen(
                            source, functions, top, variables, arrays
                        ).generate()
                    )
                else:
                    c_file = temp_path / "probe.c"
                    c_file.write_text(
                        emit_c(source, functions, top, variables, arrays),
                        encoding="utf-8",
                    )
                    compiler = find_compiler(None)
                    if compiler is None:
                        return 9, "", "no MSVC"
                    build_c(compiler[1], c_file, exe, release=True)
        except Exception as error:  # noqa: BLE001
            return 2, "", f"{type(error).__name__}: {error}"
        result = subprocess.run(
            [str(exe)], input=stdin, capture_output=True, timeout=20
        )
        return (
            result.returncode,
            result.stdout.decode("utf-8", "replace").replace("\r\n", "\n"),
            result.stderr.decode("utf-8", "replace").strip(),
        )


def main() -> int:
    rows = []
    for _name, _spec in CASES.items():
        if isinstance(_spec, tuple):
            _text = _spec[0]
            _stdin = _spec[1] if len(_spec) > 1 else bytes([10])
        else:
            _text, _stdin = _spec, bytes([10])
        rows.append((_name, run(_text, "c", _stdin), run(_text, "native", _stdin)))
    diffs = 0
    for name, c, n in rows:
        same = c[1] == n[1] and (c[0] == 0) == (n[0] == 0)
        if not same:
            diffs += 1
        print(f"{'ok  ' if same else 'DIFF'} {name}")
        if not same:
            print(f"      C  rc={c[0]} out={c[1]!r} err={c[2][:90]!r}")
            print(f"      N  rc={n[0]} out={n[1]!r} err={n[2][:90]!r}")
    print(f"\n{len(rows)} cases, {diffs} differences")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Interactive Anvil shell: type a statement, see it run, keep your variables.

The shell keeps a program made of the assignments you typed and re-runs it for
each new statement, so what you see is exactly what the compiler and the
runtime do — there is no second, "almost the same" interpreter to drift.
"""

from __future__ import annotations

import contextlib
import io
import os
import pathlib
import re
import subprocess
import sys
import tempfile

from compiler.build import build_c, find_compiler
from compiler.codegen import emit_c
from compiler.common import CompileError
from compiler.diagnostics import render
from compiler.native_codegen import NativeCodegen
from compiler.parser import parse

__all__ = ["Shell", "ReplError", "repl_main", "statement_depth", "PROMPT"]

PROMPT = "anvil> "
CONTINUE = "     | "

HELP = """\
Type Anvil statements and press Enter.

  set var(name) = "Ada"     remember a value (bare `name = "Ada"` works too)
  say "Hello, " & var(name) print something
  repeat 3 ... end          blocks span lines; the shell waits for `end`
  if var(n) > 3 ... end

Commands:
  :help     this text
  :vars     the statements the shell remembers
  :clear    forget every remembered value
  :quit     leave the shell

Bare expressions print their value (1 + 2, count(nums)).
ask var(x) prompts you and remembers the answer.
"""

_OPENERS = ("if", "repeat", "while", "for")
_ASSIGN = re.compile(r"^([A-Za-z_][\w-]*)\s*=\s*(.+)$", re.S)
_ASSIGN_TARGET = re.compile(r"^set\s+var\(([^)]+)\)\s*=", re.I)
_DECLARATION = re.compile(r"^(?:list|array)\s+[A-Za-z_][\w-]*", re.I)
_MUTATION = re.compile(r"^(?:set|add|sub)\b", re.I)
_ASK = re.compile(r'^ask\s+(?:"([^"]*)"\s*,\s*)?var\(([^)]+)\)$', re.I)
_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")


def _literal_for(value: str) -> str:
    """Turn a typed answer into an Anvil literal for the replay history."""
    if _NUMBER.match(value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
_STATEMENT_START = re.compile(
    r"^(?:set|add|sub|say|write|ask|if|elif|else|end|repeat|while|for|stop|wait|"
    r"press|output|call|list|include|fn|scene|camera|clear|display|seed)\b",
    re.I,
)


class ReplError(Exception):
    """A statement failed; the message is ready to show the user."""


@contextlib.contextmanager
def _quiet_stdout():
    """Silence compiler chatter (MSVC prints to the inherited stdout)."""
    devnull = os.open(os.devnull, os.O_WRONLY)
    saved = os.dup(1)
    os.dup2(devnull, 1)
    try:
        yield
    finally:
        os.dup2(saved, 1)
        os.close(saved)
        os.close(devnull)


def statement_depth(lines: list[str]) -> int:
    """How many blocks are still open in these lines."""
    depth = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        head = stripped.split(None, 1)[0].lower()
        if head in _OPENERS or stripped.lower().startswith("fn("):
            depth += 1
        elif stripped.lower() == "end":
            depth -= 1
    return depth


def _rewrite_assignment(statement: str) -> str:
    """Accept `x = 5` as a friendlier spelling of `set var(x) = 5`."""
    if statement.lstrip().lower().startswith("set "):
        return statement
    match = _ASSIGN.match(statement)
    if match is None:
        return statement
    return f"set var({match.group(1)}) = {match.group(2)}"


class Shell:
    """A single-user Anvil session with remembered assignments."""

    def __init__(self, backend: str = "native", ask_reader=None) -> None:
        if backend not in ("native", "c"):
            raise ValueError(f"unknown backend {backend!r}")
        self.backend = backend
        self.ask_reader = ask_reader
        self.history: list[str] = []
        self.declarations: list[str] = []

    def program(self, *statements: str) -> str:
        lines = list(self.declarations)
        lines.append("fn(main)")
        for statement in list(self.history) + list(statements):
            for line in statement.splitlines():
                if line.strip():
                    lines.append("  " + line.strip())
        lines.append("  stop")  # exits before the entry prints main's return
        lines.append("end")
        lines.append("call fn(main)")
        return "\n".join(lines) + "\n"

    def _run(self, program: str) -> tuple[bool, str]:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            source = temp_path / "repl.ANVL"
            source.write_text(program, encoding="utf-8")
            executable = temp_path / "repl.exe"
            try:
                functions, top, variables, arrays = parse(source, program)
                with _quiet_stdout():
                    if self.backend == "native":
                        executable.write_bytes(
                            NativeCodegen(
                                source, functions, top, variables, arrays
                            ).generate()
                        )
                    else:
                        c_file = temp_path / "repl.c"
                        c_file.write_text(
                            emit_c(source, functions, top, variables, arrays),
                            encoding="utf-8",
                        )
                        compiler = find_compiler(None)
                        if compiler is None:
                            raise CompileError(
                                "MSVC is not available; run the shell with "
                                "--repl-backend native"
                            )
                        build_c(compiler[1], c_file, executable, release=True)
            except CompileError as error:
                return False, render(str(error)).rstrip("\n")
            except (OSError, ValueError) as error:
                return False, f"{type(error).__name__}: {error}"
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=20
            )
        if result.returncode != 0:
            detail = (result.stdout + result.stderr).strip()
            if detail:
                return False, detail
            return False, f"the program exited with code {result.returncode}"
        return True, result.stdout

    def _names(self) -> list[str]:
        names = []
        for statement in self.history:
            match = _ASSIGN_TARGET.match(statement)
            if match is not None:
                names.append(match.group(1))
        return sorted(set(names), key=len, reverse=True)

    def _expand_variables(self, statement: str) -> str:
        """Let `say x * 3` work once `x` is remembered (it means var(x))."""
        names = self._names()
        if not names:
            return statement
        protected: list[str] = []

        def protect(match: re.Match[str]) -> str:
            protected.append(match.group(0))
            return f"\x00{len(protected) - 1}\x00"

        text = re.sub(r"var\([^)]*\)", protect, statement)
        segments = re.split(r'("(?:[^"\\]|\\.)*")', text)
        for index in range(0, len(segments), 2):
            segment = segments[index]
            for name in names:
                segment = re.sub(
                    rf"(?<![\w\x00]){re.escape(name)}(?![\w(])",
                    f"var({name})",
                    segment,
                )
            segments[index] = segment
        text = "".join(segments)
        return re.sub(r"\x00(\d+)\x00", lambda m: protected[int(m.group(1))], text)

    def eval(self, statement: str) -> str:
        """Run one statement and return what the user should see."""
        statement = statement.strip()
        while statement.endswith(";"):
            statement = statement[:-1].rstrip()
        if not statement:
            return ""
        declaration = _DECLARATION.match(statement)
        if declaration is not None:
            self.declarations.append(statement)
            ok, output = self._run(self.program())
            if not ok:
                self.declarations.pop()
                raise ReplError(output)
            return ""
        ask = _ASK.match(statement)
        if ask is not None:
            # A child process cannot read the terminal here: the shell has
            # already buffered the input. Ask in-process and remember the answer.
            prompt, name = ask.group(1) or "", ask.group(2)
            if self.ask_reader is None:
                raise ReplError(
                    "ask needs an interactive terminal; run the program with "
                    "python compiler/anvil.py file.ANVL instead"
                )
            answer = self.ask_reader(prompt)
            self.history.append(f"set var({name}) = {_literal_for(answer)}")
            return ""
        rewritten = _rewrite_assignment(statement)
        assignment = rewritten != statement or bool(_MUTATION.match(rewritten))
        rewritten = self._expand_variables(rewritten)
        if not _STATEMENT_START.match(rewritten):
            # A bare expression: show its value like any calculator would.
            rewritten = "say " + rewritten
        ok, output = self._run(self.program(rewritten))
        if not ok:
            raise ReplError(output)
        if not assignment:
            return output
        target = _ASSIGN_TARGET.match(rewritten)
        self.history.append(rewritten)
        if target is None:
            return output
        ok, value = self._run(self.program(f"say var({target.group(1)})"))
        if not ok:
            return output
        return f"{target.group(1)} = {value.strip()}\n"


HELLO_PROGRAM = """fn(main)
  say "Hello from Anvil!"
  say "This program was compiled and run just now."
end
call fn(main)
"""


def hello_main(backend: str = "native", stdout: io.TextIOBase | None = None) -> int:
    """Build and run a greeting program so the first command always works."""
    stdout = stdout if stdout is not None else sys.stdout
    shell = Shell(backend=backend)
    ok, output = shell._run(HELLO_PROGRAM)
    if not ok:
        stdout.write(output.rstrip("\n") + "\n")
        return 1
    stdout.write(output)
    stdout.write(
        "\nThat greeting was built and executed by the compiler you just ran.\n"
        "Next steps:\n"
        "  put the same program in hello.ANVL, then\n"
        "  python compiler/anvil.py hello.ANVL -o hello.exe\n"
        "or explore interactively:\n"
        "  python compiler/anvil.py --repl\n"
    )
    return 0


def repl_main(
    backend: str = "native",
    stdin: io.TextIOBase | None = None,
    stdout: io.TextIOBase | None = None,
) -> int:
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout

    def ask_reader(prompt: str) -> str:
        if prompt:
            stdout.write(prompt)
            stdout.flush()
        answer = stdin.readline()
        return answer.rstrip("\r\n")

    shell = Shell(backend=backend, ask_reader=ask_reader)
    stdout.write(
        f"Anvil shell ({backend} backend): every line is compiled and run, and\n"
        'your variables are remembered. Try:  say "Hello, " & "world"\n'
        "     x = 2\n"
        "     say x * 3\n"
        ":help lists the commands, :quit leaves.\n\n"
    )
    pending: list[str] = []
    while True:
        stdout.write(PROMPT if not pending else CONTINUE)
        stdout.flush()
        line = stdin.readline()
        if not line:
            stdout.write("\n")
            return 0
        line = line.rstrip("\r\n")
        if not pending:
            command = line.strip().lower()
            if command in (":quit", ":q", ":exit", "quit", "exit"):
                return 0
            if command in (":help", "help", "?"):
                stdout.write(HELP)
                continue
            if command in (":vars", ":state", ":history"):
                if shell.declarations or shell.history:
                    for statement in shell.declarations + shell.history:
                        stdout.write(f"  {statement}\n")
                else:
                    stdout.write("  (nothing remembered yet)\n")
                continue
            if command in (":clear", ":reset"):
                shell.history.clear()
                shell.declarations.clear()
                stdout.write("cleared\n")
                continue
        pending.append(line)
        if statement_depth(pending) > 0:
            continue
        statement = "\n".join(pending)
        pending.clear()
        if not statement.strip():
            continue
        try:
            output = shell.eval(statement)
        except ReplError as error:
            stdout.write(str(error).rstrip("\n") + "\n")
            continue
        if output:
            stdout.write(output if output.endswith("\n") else output + "\n")

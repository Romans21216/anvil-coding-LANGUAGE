# Contributing to Anvil

Anvil is an early game-language and runtime project. Read `README.md`, `docs/LANGUAGE.md`, `docs/ENGINE.md`, and `docs/COMPILER.md` before changing syntax or runtime behavior. Keep the implementation, examples, tests, VS Code grammar, and docs in sync.

## Development checks

```powershell
python -m unittest discover -s tests -v
npm test --prefix vscode-extension
```

Use the compiler commands in `docs/COMPILER.md` for a native build. Report the compiler and platform when a check is unavailable.

## Bug reports

Only verified defects belong in bug issues. Include a minimal `.ANVL` example, exact build/run steps, expected behavior, actual behavior, and platform/compiler details. Keep roadmap requests and missing planned features separate from bugs.

- Issues found by an independent final-review critic use the title `Codex Bugs: <short description>` and the `Codex Bugs` label.
- Bugs reported by repository owner `Romans21216` use the title `Romans21216-Bugs: <short description>` and the same `Codex Bugs` label.
- A fixed defect is not reopened as an open issue unless it still reproduces.


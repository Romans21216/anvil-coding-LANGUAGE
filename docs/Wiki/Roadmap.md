# Roadmap

The complete requested 450-point improvement list is maintained only in the body and comments of [GitHub issue #23](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23). It spans language semantics, GPU/CPU renderers, graphics/assets, game systems, networking, performance, testing, platform support, documentation, and release engineering. The repository keeps only a link to the issue and a compact ledger of audited work.

See the [request completion matrix](../COMPLETION_MATRIX.md) for a traceable implemented/partial/missing audit of the original request.

## Current milestone

Implemented in the current prototype:

- `.ANVL` compiler to C and Windows executable.
- Numeric function parameters, numeric return values, recursion, and function-local state.
- `while condition ... end` loops, with compiler validation and native execution tests.
- Inclusive numeric `for local(name) = start to end [step amount] ... end` loops with ascending/descending steps and nested-loop checks.
- Fixed-size global and function-local numeric arrays declared with `array name(size)`, with zero initialization, per-call heap storage for local arrays, checked cleanup and a 16 MiB active-call budget, and runtime-checked zero-based reads/writes.
- Basic 2D and 3D software-rendered scenes, camera movement, and field of view.
- Built-in `ray_sphere` with CPU BVH, plus projected sphere bounds regression coverage.
- Basic Windows UDP host/join exchanging one numeric value.
- Fixed-step 2D circle and axis-aligned box physics for up to 128 bodies, with force, gravity, restitution, mixed-shape overlap queries, and collision response.
- VS Code syntax extension and sample programs.

## Next foundational work

1. Modularize the compiler into lexer/tokenization, parser/AST, semantic checks, C backend, and build driver.
2. Define stable lexical, scoping, initialization, type, return, and error rules in a versioned language specification.
3. Add dynamically sized collections, user-defined structures, and basic static data types with tests before growing the game API.
4. Extract a platform abstraction and configurable render-surface/window layer; preserve the CPU renderer as a first-class backend.
5. Add a true GPU raster backend only after defining parity and fallback contracts. Keep CPU BVH ray tracing independent; add DXR or Embree only as optional backends.
6. Replace numeric UDP with versioned bounded messages and peer/session lifecycle before expanding online play.
7. Extend the initial circle physics with polygons, 3D bodies, friction, joints, and spatial acceleration only alongside tests and examples.
8. Benchmark actual compiler, frame, memory, and ray-tracing performance before making speed claims.

Every feature should have source tests, executable integration evidence where practical, updated references/examples, and a release note. Planned features must not be described as implemented.


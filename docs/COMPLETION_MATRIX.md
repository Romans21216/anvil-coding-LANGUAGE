# Anvil request completion matrix

The complete backlog lives only in GitHub issue [#23](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23) and its comments. This matrix summarizes capabilities and limits. Review scores and test counts belong to the exact snapshots in [QA_REPORT.md](QA_REPORT.md), [plain text evaluation](ANVIL_EVALUATION.txt) and [structured state](CODEX_AUTONOMOUS_STATE.json).

| Requested capability | Current implementation | Remaining work |
|---|---|---|
| Simple `.ANVL` language with functions | Parser, semantic checks, numeric functions/returns/recursion, scalar globals/locals, branches and loops work. | Rich types, general strings, collections and broader standard library. |
| Direct source-to-executable compiler without C/Rust | Experimental backend emits AMD64 machine code and Windows PE32+ directly. Numeric programs, checked global/local arrays, input/procedural functions and initial 2D rectangles/circles/lines and literal Unicode text work. | Complete native language/runtime parity, default migration. Broader engine builds still use the C/MSVC default. |
| Source reuse and dependency selection | Local `include "relative.ANVL"` graphs merge source once, preserve physical locations and apply graph limits. Native code generation selects reachable functions. | Namespaces, separate objects/linking, registries, binary plugins and automatic external package resolution. All globals/initializers remain included. |
| 2D and 3D worlds with cameras | C runtime has software primitives, camera controls, HUD composition and bounded BMP sprites. Direct backend has a buffered Win32 rectangle/circle/line/literal-text renderer. | Native 3D/camera/general strings/numeric text/alpha, GPU rendering, scene/asset systems and visual coverage. |
| Ray tracing as built-ins | C runtime provides `ray_sphere`, `ray_backend` and `ray_backend_available`. CPU BVH supports up to 32 spheres per batch. | Actual selectable DXR/RTX and Embree backends; native implementation. Unavailable backends currently return unavailable or reject selection. |
| RNG and Perlin-style noise | Seeded RNG, deterministic gradient noise/fBm and basic math work in both paths; native procedural helpers use Anvil source. | Broader native math parity and performance evidence. |
| Input and camera controls | C runtime exposes keyboard/camera and viewport-mapped mouse input. Native input exposes keyboard states, client-pixel coordinates, mouse buttons/wheel and capture/focus handling. | Complete native camera behavior; untouched OS coordinate-dispatch integration coverage (#63). |
| Physics | C runtime has fixed-step 2D circle/axis-aligned-box contacts, restitution and friction, with configurable active capacity up to 128. Tests are in `tests/test_compiler.py`. | Native port, rotation, CCD, broad phase, polygons/3D bodies, joints and stability work. |
| Media/assets/audio | C runtime safely loads bounded uncompressed BMPs and draws clipped/scaled alpha-blended 2D sprites. | Native assets, other formats, rotation/atlases/animation, 3D textures and audio. |
| Multiplayer | C runtime exchanges a numeric UDP value with one peer for trusted LAN experiments. | Native networking, reliability, structured replication, authentication, encryption and peer lifecycle. |
| Forge and additional executable/OS outputs | Requirements are preserved as additions to issue #23. | Forge executable/media formats, multiple platforms/targets, assembly/UEFI/freestanding compiler support and separate bootloader/kernel/OS libraries. |
| VS Code tooling | Source/package 0.1.11 registers Anvil and `.ANVL`/`.anvl`, with tested TextMate scopes including includes. Installed 0.1.4 had earlier ray-backend visual verification. | 0.1.11 indentation/folding corrections are independently verified (#69). Fresh visible verification of newer tokens (#24); user preference preserves 0.1.4. |
| Minimal storage, memory and CPU | Native dependency selection avoids generating unused functions/imports; direct outputs have measured artifact sizes in the review evidence. | Reproducible compiler/runtime/rendering/physics/ray benchmarks (#14), broader optimization and resource budgets. Small samples do not prove optimal efficiency. |

The full engine goal remains active. A green subset test suite or historical prototype score does not prove completion of missing systems. The [audited ledger](IMPLEMENTATION_STATUS.md) records item-specific evidence without copying the full backlog.

Native project builds accept `.ANVLproj` with `--backend native`. The existing `name` supplies the Unicode window title, `entry` resolves inside the project directory, and `[engine].fixed_hz` accepts integer rates1–240 (default60). Includes may span the project tree. Native graphical updates, `time()` and `delta()` use that rate. Direct source titles and console behavior retain their defaults. Unsupported native features fail explicitly without invoking C/Rust.

Native local arrays are independently verified with allocation/lifetime regressions; exact review evidence is in QA_REPORT.md. Full engine/Forge/OS scope remains incomplete.

Historical numeric ABI review: independently reviewed `ecdf68109fd5932d8ae572a8f16446194e93b935` remains 76/100, with 162 tests passing in 139.160s. Shared argument transport/addressing is verified; general typed lowering, systems ABI, object linking and native engine parity remain incomplete.

Historical independent drawing review: `f11240c19d708718d8b94bae5f3b3764df435f88`,73/100,168 tests in176.154s. Native circles/lines verified; #79 default C-circle offscreen traversal stall confirmed and open. Full scope remains incomplete.

Historical independent correction review: `b0e02422d6447b5f6f289797e7211a9870aff26d`,73/100,169 tests in203.685s. Original #79 timeout fixed; extreme negative-tangent membership residual remains open. Full goal incomplete.

Latest independent review: `139f9241a7af1c3a137d0f6408fab0bfb5141662`,76/100,169 tests in165.552s. Both #79 failures verified fixed;110 independent full-frame guard cases pass. Full goal remains incomplete.

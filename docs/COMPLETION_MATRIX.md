# Anvil request completion matrix

The complete backlog lives only in GitHub issue [#23](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23) and its comments. This matrix summarizes capabilities and limits. Review scores and test counts belong to the exact snapshots in [QA_REPORT.md](QA_REPORT.md), [plain text evaluation](ANVIL_EVALUATION.txt) and [structured state](CODEX_AUTONOMOUS_STATE.json).

| Requested capability | Current implementation | Remaining work |
|---|---|---|
| Simple `.ANVL` language with functions | Parser, semantic checks, numeric functions/returns/recursion, scalar globals/locals, branches and loops work. | Rich types, general strings, collections and broader standard library. |
| `.ANVL`-to-executable compiler | The primary CLI parses and validates Anvil, compiles through temporary C, invokes MSVC, and produces machine-code Windows executables in one command. Generated C, object files and the MSVC helper are removed by default; `--generated-c` preserves C while building and `--emit-c` writes C only. An optional experimental direct-x64 backend remains available for a smaller subset. | Broader portability and C-toolchain coverage; direct backend parity is not required for the main workflow. |
| Source reuse and dependency selection | Local whole-file includes and selective `include fn(name) -- "file.ANVL"` imports preserve physical locations and apply graph limits. Qualified calls isolate helper/state identities; aliases share a canonical module. | Separate objects/linking, registries, binary plugins and automatic external package resolution. Required top-level initializers remain; unused global declarations are pruned after reachability analysis. |
| 2D and 3D worlds with cameras | C runtime has software primitives, camera controls, HUD composition and bounded BMP sprites. Direct backend has a direct BGRX/RGBA-shape renderer with buffered Unicode text. | Native 3D/camera/general strings/numeric text/text opacity, GPU rendering, scene/asset systems and visual coverage. |
| Ray tracing as built-ins | C runtime provides `ray_sphere`, `ray_backend` and `ray_backend_available`. CPU BVH supports up to 32 spheres per batch. | Actual selectable DXR/RTX and Embree backends; native implementation. Unavailable backends currently return unavailable or reject selection. |
| RNG and Perlin-style noise | Seeded RNG, deterministic gradient noise/fBm and basic math work in both paths; native procedural helpers use Anvil source. | Broader native math parity and performance evidence. |
| Input and camera controls | C runtime exposes keyboard/camera and viewport-mapped mouse input. Native input exposes keyboard states, client-pixel coordinates, mouse buttons/wheel and capture/focus handling. | Complete native camera behavior; untouched OS coordinate-dispatch integration coverage (#63). |
| Physics | C runtime has fixed-step 2D circle/axis-aligned-box contacts, restitution and friction, with configurable active capacity up to 128. Tests are in `tests/test_compiler.py`. | Native port, rotation, CCD, broad phase, polygons/3D bodies, joints and stability work. |
| Media/assets/audio | C runtime safely loads bounded uncompressed BMPs and draws clipped/scaled alpha-blended 2D sprites. | Native assets, other formats, rotation/atlases/animation, 3D textures and audio. |
| Multiplayer | C runtime exchanges a numeric UDP value with one peer for trusted LAN experiments. | Native networking, reliability, structured replication, authentication, encryption and peer lifecycle. |
| Forge and additional executable/OS outputs | Requirements are preserved as additions to issue #23. | Forge executable/media formats, multiple platforms/targets, assembly/UEFI/freestanding compiler support and separate bootloader/kernel/OS libraries. |
| VS Code tooling | Source/package 0.1.13 registers Anvil and `.ANVL`/`.anvl`, with automated TextMate scopes for metadata, callbacks, `varl`, compact networking, and double-dash includes. Installed 0.1.4 remains unchanged. | Fresh visible verification of newer tokens (#24); user preference preserves installed 0.1.4. |
| Minimal storage, memory and CPU | C generation omits unreachable Anvil functions and unused global scalar/array declarations while retaining callback targets, transitive calls, engine roots, and top-level initialization. Projects can configure per-function local-array elements and aggregate active-call local-array memory. Default builds remove generated C and object/helper intermediates, with explicit C preservation options. | C runtime subsystems and feature modules are not yet selectively linked. Reproducible compiler/runtime/rendering/physics/ray benchmarks (#14) and resource budgets remain. These changes do not establish optimal efficiency. |

The full engine goal remains active. A green subset test suite or historical prototype score does not prove completion of missing systems. The [audited ledger](IMPLEMENTATION_STATUS.md) records item-specific evidence without copying the full backlog.

Latest independent full review: base `87e23d6943028222619f9febe0ed970e8d1a7ed7`, source/test SHA256 `57b0392fa1a325a23fda8d1aa202e7299b141e92d390b1cc518cc0b0ad22db5c`, implementation SHA256 `24ad1dc17364afc5c94eb80ae8dcd8fbfafa8113f5a579c3a7c39683cd6954ac`; score79/100 FAIL against98 after criterion38 sync (independent record-parity recheck PASS);233 tests independently passed in253.611s and locally in269.749s. Project-configurable array limits now flow through both backends and included sources; issue #90 native diagnostic fix is independently verified. Items #80/#81 have partial progress. #87–#90 are fixed; #88–#90 closed; #90 was fixed and independently verified before closure. #123 remains partial because runtime subsystems and package features are not selectively linked. The complete requirements remain only in #23. See the full50 rubric in [QA_REPORT.md](QA_REPORT.md).

Native project builds accept `.ANVLproj` with `--backend native`. The existing `name` supplies the Unicode window title, `entry` resolves inside the project directory, and `[engine].fixed_hz` accepts integer rates1–240 (default60). Includes may span the project tree. Native graphical updates, `time()` and `delta()` use that rate. Direct source titles and console behavior retain their defaults. Unsupported native features fail explicitly without invoking C/Rust.

Native local arrays are independently verified with allocation/lifetime regressions; exact review evidence is in QA_REPORT.md. Full engine/Forge/OS scope remains incomplete.

Historical numeric ABI review: independently reviewed `ecdf68109fd5932d8ae572a8f16446194e93b935` remains 76/100, with 162 tests passing in 139.160s. Shared argument transport/addressing is verified; general typed lowering, systems ABI, object linking and native engine parity remain incomplete.

Historical independent drawing review: `f11240c19d708718d8b94bae5f3b3764df435f88`,73/100,168 tests in176.154s. Native circles/lines verified; #79 default C-circle offscreen traversal stall confirmed and open. Full scope remains incomplete.

Historical independent correction review: `b0e02422d6447b5f6f289797e7211a9870aff26d`,73/100,169 tests in203.685s. Original #79 timeout fixed; extreme negative-tangent membership residual remains open. Full goal incomplete.

Historical independent circle-fix review: `139f9241a7af1c3a137d0f6408fab0bfb5141662`,76/100,169 tests in165.552s. Both #79 failures verified fixed;110 independent full-frame guard cases pass. Full goal remains incomplete.

Historical independent text review: `68ff824b53cae9952fbfbce7fd27d29ac4bfc7f2`,76/100,175 tests in218.389s. Native literal Unicode text independently verified; no new defect. General strings/numeric HUD/layout and full engine/Forge/OS scope remain incomplete.

Historical independent surface review: `4f5c981bddf2796e56b6bea14d8f575d692b6da5`,76/100,180 tests in286.162s. Native DIB/RGBA shapes independently verified, no new defect. Full engine/Forge/OS scope remains incomplete.

Historical independent selective review: `957ee124402e0ba773971aaee24c48c8b277929a`, 71/100, 192 tests in 323.089s. Full independent review of957ee12:71/100 FAIL against98, categories11/15/14/16/15;192 tests passed in323.089s. Selective imports implemented, but #81 supplementary-Unicode C literal encoding and #82 private function/array reference bypass remain open. Full engine/Forge/OS/targets/types/backends/benchmarks/tooling and #63 remain incomplete. Goal stays active.

Latest independent selective review: `b76fc02a1f6ea9ab24f7af004e8a0981ba249252`, 76/100, 194 tests in 281.445s. Full independent review of b76fc02:76/100 FAIL against98, categories12/18/14/17/15;194 tests passed in 281.445s. Selective imports, qualified calls, private helpers/state and aliases verified; #81 supplementary C UTF-8 metadata and #82 private source-reference bypass independently fixed. Full native engine/Forge/OS/types/targets/actual ray backends/benchmarks/tooling and #63 remain incomplete. Goal stays active.


The user clarified in #23 that C/assembly may support UEFI/kernel work while OS user-interface layers should be authored in Anvil and compile into loadable executables; optional game, graphics, input, media, ray-tracing and networking features should be modular imports. The current compiler does not yet meet those OS/package targets.

Six-record record-only parity audit passed for the current candidate; score and implementation snapshot are unchanged.
Published reviewed candidate: `b4e8a20ee511388123f4982001ac997c6c720e4f`. Issue #90 closed; latest evaluation comment: https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23#issuecomment-6583162339.

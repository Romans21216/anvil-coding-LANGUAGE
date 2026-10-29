# Anvil Language Support for Visual Studio Code

This extension registers the Anvil language identifier (`anvil`) for `.ANVL` files and provides TextMate syntax colors plus editor pairing, comments, indentation, and folding rules. It highlights `include "relative/library.ANVL"` directives, function declarations and parameters, calls, global/local variables, fixed-array declarations/indexing, engine commands, ray-tracing backend selection, mouse and keyboard input, image/sprite, ray-tracing, and 2D physics built-ins, operators, and literals. It targets **Visual Studio Code**, not the separate Visual Studio IDE.

## Install locally

1. Open the `vscode-extension` folder in VS Code.
2. Press `F5` to launch an Extension Development Host.
3. Open `examples/first_world.ANVL` in the development host to see Anvil token scopes.

To install the included package, use **Extensions: Install from VSIX...** and select the current version's `.vsix` package. To rebuild it, run `npx --yes @vscode/vsce package --allow-missing-repository` from this folder.

## Highlighted constructs

The grammar scopes comments, escaped strings, `fn(name)` declarations, `call fn(name)` calls, `array name(size)` declarations and `array(name,index)` accesses, `var(...)` and `flag(...)` bindings, engine commands, control keywords, constants, rendering, ray backend, keyboard and mouse input built-ins, image/sprite resource built-ins, networking, and physics built-ins including `physics_capacity` and `body_friction`, numbers, operators, and punctuation. Standard TextMate scopes are used so installed themes supply the colors.

## Validation

Run `npm ci` once, then `npm run validate` to validate the JSON manifest, language configuration, grammar structure, and representative Anvil tokens using the included checks.


Version 0.1.11 corrects indentation and folding for function, if, while, for, else and end statements, including trailing comments. Automated configuration tests exercise real control-flow headers and unrelated text. This package has not been installed or visibly verified; installed 0.1.4 is preserved per user preference.

Version 0.1.12 adds selective imports (`include fn(move) - "lib/player.ANVL" as input`) and qualified calls (`call fn(move - input, 10)`). Automated TextMate token tests cover selectors, source qualifiers, aliases, nested calls and existing hyphenated names. The package is statically verified only; installed 0.1.4 remains unchanged.

# Anvil Language Support for Visual Studio Code

This extension registers the Anvil language identifier (`anvil`) for `.ANVL` files and provides TextMate syntax colors plus editor pairing, comments, indentation, and folding rules. It highlights function declarations and parameters, calls, global/local variables, fixed-array declarations/indexing, engine commands, ray-tracing backend selection, ray-tracing and 2D physics built-ins, operators, and literals. It targets **Visual Studio Code**, not the separate Visual Studio IDE.

## Install locally

1. Open the `vscode-extension` folder in VS Code.
2. Press `F5` to launch an Extension Development Host.
3. Open `examples/first_world.ANVL` in the development host to see Anvil token scopes.

To install the included package, use **Extensions: Install from VSIX...** and select `anvil-language-support-0.1.6.vsix`. To rebuild it, run `npx --yes @vscode/vsce package --allow-missing-repository` from this folder.

## Highlighted constructs

The grammar scopes comments, escaped strings, `fn(name)` declarations, `call fn(name)` calls, `array name(size)` declarations and `array(name,index)` accesses, `var(...)` and `flag(...)` bindings, engine commands, control keywords, constants, rendering, ray backend, networking, and physics built-ins including `physics_capacity`, numbers, operators, and punctuation. Standard TextMate scopes are used so installed themes supply the colors.

## Validation

Run `npm ci` once, then `npm run validate` to validate the JSON manifest, language configuration, grammar structure, and representative Anvil tokens using the included checks.


const fs = require('node:fs');
const path = require('node:path');
const { Registry, INITIAL, parseRawGrammar } = require('vscode-textmate');
const oniguruma = require('vscode-oniguruma');

const root = path.resolve(__dirname, '..');
const manifestPath = path.join(root, 'package.json');
const configPath = path.join(root, 'language-configuration.json');
const grammarPath = path.join(root, 'syntaxes', 'anvil.tmLanguage.json');
const samplePath = path.resolve(root, '..', 'examples', 'first_world.ANVL');
const arraysSamplePath = path.resolve(root, '..', 'examples', 'arrays.ANVL');
const physicsSamplePath = path.resolve(root, '..', 'examples', 'physics.ANVL');
const mouseSamplePath = path.resolve(root, '..', 'examples', 'mouse_input.ANVL');
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
JSON.parse(fs.readFileSync(grammarPath, 'utf8'));
const sample = fs.readFileSync(samplePath, 'utf8');
const arraysSample = fs.readFileSync(arraysSamplePath, 'utf8');
const physicsSample = fs.readFileSync(physicsSamplePath, 'utf8');
const mouseSample = fs.readFileSync(mouseSamplePath, 'utf8');
const check = (condition, message) => { if (!condition) throw new Error(message); };

check(manifest.contributes.languages.some(x => x.id === 'anvil' && x.extensions.includes('.ANVL')), 'Anvil language or extension is not registered');
check(manifest.capabilities?.untrustedWorkspaces?.supported === true, 'syntax-only language support should work in Restricted Mode');
check(manifest.contributes.grammars.some(x => x.language === 'anvil' && x.scopeName === 'source.anvil' && x.path === './syntaxes/anvil.tmLanguage.json'), 'Anvil grammar contribution is missing or mismatched');
check(config.comments.lineComment === '#', 'line comment configuration is missing');
check(config.brackets.some(pair => pair[0] === '(' && pair[1] === ')'), 'parenthesis pairing is missing');

async function main() {
  const wasmBuffer = fs.readFileSync(require.resolve('vscode-oniguruma/release/onig.wasm'));
  await oniguruma.loadWASM(wasmBuffer.buffer.slice(wasmBuffer.byteOffset, wasmBuffer.byteOffset + wasmBuffer.byteLength));
  const registry = new Registry({
    onigLib: Promise.resolve({
      createOnigScanner: sources => new oniguruma.OnigScanner(sources),
      createOnigString: value => new oniguruma.OnigString(value)
    }),
    loadGrammar: async scopeName => scopeName === 'source.anvil'
      ? parseRawGrammar(fs.readFileSync(grammarPath, 'utf8'), grammarPath)
      : null
  });
  const grammar = await registry.loadGrammar('source.anvil');
  check(grammar, 'TextMate grammar did not load');

  function scopesAt(line, needle) {
    const result = grammar.tokenizeLine(line, INITIAL);
    const index = line.indexOf(needle);
    check(index >= 0, `test token '${needle}' is missing from '${line}'`);
    const token = result.tokens.find(t => t.startIndex <= index && index < t.endIndex);
    check(token, `no token scope covers '${needle}'`);
    return token.scopes;
  }
  function expect(line, needle, scope) {
    const scopes = scopesAt(line, needle);
    check(scopes.includes(scope), `'${needle}' expected ${scope}; got ${scopes.join(' ')} in ${line}`);
  }
  expect('fn(update)', 'fn', 'keyword.declaration.function.anvil');
  expect('language version 1', 'language', 'keyword.control.anvil');
  expect('language version 1', 'version', 'keyword.control.anvil');
  expect('language version 1', '1', 'constant.numeric.integer.anvil');
  expect('fn(update)', 'update', 'entity.name.function.anvil');
  expect('fn(add, left, right)', 'add', 'entity.name.function.anvil');
  expect('fn(add, left, right)', 'left', 'variable.parameter.anvil');
  expect('call fn(reset-player)', 'reset-player', 'variable.function.anvil');
  expect('call fn(add, 2, 3)', 'add', 'variable.function.anvil');
  expect('for local(index) = 1 to 5 step 2', 'for', 'keyword.control.anvil');
  expect('for local(index) = 1 to 5 step 2', 'to', 'keyword.control.anvil');
  expect('for local(index) = 1 to 5 step 2', 'step', 'keyword.control.anvil');
  expect('array scores(4)', 'array', 'storage.type.array.anvil');
  expect('array scores(4)', 'scores', 'variable.other.array.anvil');
  expect('array(scores, local(index))', 'array', 'support.function.anvil');
  expect('set var(player-health) = 24', 'player-health', 'variable.other.anvil');
  expect('set local(temporary) = 1', 'temporary', 'variable.other.anvil');
  expect('set flag(game-running) = true', 'game-running', 'variable.other.anvil');
  expect('display cube(0, 0, 0, 1.8)', 'display', 'support.function.engine.anvil');
  expect('display cube(0, 0, 0, 1.8)', 'cube', 'support.function.anvil');
  expect('display ray_sphere(0, 0, 0, 1)', 'ray_sphere', 'support.function.anvil');
  expect('set local(ok) = ray_backend("bvh")', 'ray_backend', 'support.function.anvil');
  expect('set local(available) = ray_backend_available("dxr")', 'ray_backend_available', 'support.function.anvil');
  expect('set var(ball) = body_create(0, 0, 1, 1)', 'body_create', 'support.function.anvil');
  expect('set var(box) = body_create_box(0, 0, 2, 1, 0)', 'body_create_box', 'support.function.anvil');
  expect('set var(ok) = body_friction(var(box), 0.8)', 'body_friction', 'support.function.anvil');
  expect('set var(capacity) = physics_capacity(64)', 'physics_capacity', 'support.function.anvil');
  expect('set var(contacts) = physics_step()', 'physics_step', 'support.function.anvil');
  expect('set var(x) = mouse_x()', 'mouse_x', 'support.function.anvil');
  expect('set var(y) = mouse_y()', 'mouse_y', 'support.function.anvil');
  expect('set var(clicked) = mouse_pressed("left")', 'mouse_pressed', 'support.function.anvil');
  expect('set var(held) = mouse_held("right")', 'mouse_held', 'support.function.anvil');
  expect('set var(wheel) = mouse_wheel()', 'mouse_wheel', 'support.function.anvil');
  expect('set var(size) = 1.8', '1.8', 'constant.numeric.float.anvil');
  expect('set var(size) = 18', '18', 'constant.numeric.integer.anvil');
  expect('set var(size) = 3 + 4', '+', 'keyword.operator.anvil');
  expect('set var(title) = "fn(not-a-call)"', 'fn(not-a-call)', 'string.quoted.double.anvil');
  expect('# scene 3d', 'scene', 'comment.line.number-sign.anvil');
  const unrelated = scopesAt('functionality = 1', 'functionality');
  check(!unrelated.some(scope => scope.startsWith('keyword.control') || scope.startsWith('support.function') || scope.startsWith('storage.')), `unrelated identifier received a keyword/API scope: ${unrelated.join(' ')}`);

  for (const required of ['fn(update)', 'var(spin)', '"Anvil Engine"', 'scene 3d', 'ray_sphere(', 'camera control(']) {
    check(sample.includes(required), `sample does not demonstrate ${required}`);
  }
  for (const required of ['array scores(4)', 'array(scores, local(index))']) {
    check(arraysSample.includes(required), `array sample does not demonstrate ${required}`);
  }
  for (const required of ['body_create(', 'body_force(', 'physics_step()']) {
    check(physicsSample.includes(required), `physics sample does not demonstrate ${required}`);
  }
  for (const required of ['mouse_x()', 'mouse_y()', 'mouse_pressed("left")', 'mouse_wheel()']) {
    check(mouseSample.includes(required), `mouse sample does not demonstrate ${required}`);
  }
  console.log('PASS: VS Code manifest/config are valid; TextMate grammar loads and token scopes match Anvil samples.');
  registry.dispose();
}

main().catch(error => { console.error(error.stack || String(error)); process.exitCode = 1; });


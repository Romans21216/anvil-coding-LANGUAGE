# Extension functions: C++, C# and Anvil code the compiler links in

An extension is a library plus a small JSON manifest. Register it and its
functions behave like builtins — `gcd(48, 18)` — on **both** backends.

```
anvil program.ANVL --extension mathx.json -o program.exe
```

## The ABI

Every entry point takes and returns `double` (Anvil's `number`) and uses the
Windows x64 calling convention, which is what both backends already emit.
Up to four arguments cross in `XMM0`–`XMM3`.

**C++**

```cpp
extern "C" __declspec(dllexport) double anvil_ext_gcd(double a, double b) {
  long x = (long)a, y = (long)b;
  while (y != 0) { long t = x % y; x = y; y = t; }
  return (double)x;
}
```

Build it as a DLL (`cl /LD mathx.cpp`); MSVC also writes `mathx.lib`.

**C#** — publish with NativeAOT, which turns the library into a native DLL with
C exports:

```csharp
using System.Runtime.InteropServices;

public static class MathX
{
    [UnmanagedCallersOnly(EntryPoint = "anvil_ext_triple")]
    public static double Triple(double value) => value * 3.0;
}
```

```
dotnet publish MathXLib.csproj -c Release -r win-x64 -p:PublishAot=true -p:NativeLib=Shared
```

NativeAOT ships no `.lib`. Leave `lib` out of the manifest and the compiler
builds one from the manifest's exports with `lib.exe` before linking.

**Anvil** — no DLL at all; point `source` at a `.ANVL` file. Its functions are
compiled into the program and called normally: `call fn(mean2, 4, 10)`.

## The manifest

```json
{
  "name": "mathx",
  "kind": "dll",
  "dll": "mathx.dll",
  "lib": "mathx.lib",
  "functions": [
    {"name": "gcd", "symbol": "anvil_ext_gcd", "arity": 2},
    {"name": "lcm", "symbol": "anvil_ext_lcm", "arity": 2}
  ]
}
```

| field | meaning |
|---|---|
| `name` | identifier for the extension; also the name used in error messages |
| `kind` | `dll` (default) or `anvil` |
| `dll` | path to the library, relative to the manifest |
| `lib` | optional import library; generated from `functions` when absent |
| `source` | for `kind: "anvil"`, the `.ANVL` file to compile in |
| `functions[].name` | the name Anvil code calls |
| `functions[].symbol` | the exported symbol in the DLL |
| `functions[].arity` | argument count, 0–4; checked at compile time |

Paths are resolved relative to the manifest, so a manifest can live beside the
library it describes.

## What the compiler does

1. Validates the manifest, refusing names that collide with a builtin or with
   another extension.
2. Registers each function as a builtin name, so arity errors read like Anvil's
   own: `gcd() expects 2 argument(s), got 1`.
3. **C backend** — emits `__declspec(dllimport) double anvil_ext_gcd(double, double);`
   and links the `.lib` (generated first when the manifest has no `lib`).
4. **Native backend** — adds the symbol to the PE import table of the DLL, so
   the produced executable calls it directly with no linker involved.
5. Copies every registered DLL beside the executable it just built.

Because the generated C only names the symbols, the build cache is skipped
whenever an extension is active — a rebuilt DLL can't hide behind a cache hit.

## Limits

- Numbers only: text and records do not cross the extension boundary yet.
- At most four arguments (XMM0–XMM3); more would need stack slots the extension
  ABI does not define.
- The DLL must sit beside the executable at run time (the compiler puts it
  there) or somewhere on `PATH`.
- `kind: "anvil"` extensions are ordinary Anvil functions: call them with
  `call fn(name, ...)`, not as bare builtins.

## Worked example

`extensions/mathx.cpp` and `extensions/mathx.json` in this repository:

```
cl /LD extensions/mathx.cpp /Fe:extensions/mathx.dll
anvil examples/gcd.ANVL --extension extensions/mathx.json -o gcd.exe
```

Both backends print the same answers; `tests/test_extensions.py` builds the DLL
once and asserts it on `--backend c` and `--backend native`.

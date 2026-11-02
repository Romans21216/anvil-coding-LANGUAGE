# Anvil Windows file icons

Anvil supplies three Windows icons based on the pixel-art reference:

| File type | Icon | Windows behavior |
| --- | --- | --- |
| `.ANVLproj` | Anvil with gear | Project manifest; opens in VS Code |
| Anvil-built `.exe` | Hammer and anvil | Embedded in each executable built by either backend |
| `.ANVL` | Anvil with pencil | Editable source; opens in VS Code |

## Register source and project icons

On Windows, run this from the repository root in PowerShell:

```powershell
.\scripts\install_windows_icons.ps1
```

This registers `.ANVL` and `.ANVLproj` for the current Windows user and copies their icons into `%LOCALAPPDATA%\Anvil\icons`. It leaves an existing association or protected Windows `UserChoice` untouched and reports a conflict instead of replacing it. It does not change Windows' global `.exe` association.

To remove the per-user registrations and copied icons:

```powershell
.\scripts\install_windows_icons.ps1 -Uninstall
```

Windows may retain already displayed file icons in its Explorer cache. Refresh or reopen the folder; if old icons remain, sign out and back in to refresh the shell. New Anvil executables contain their icon resource immediately.

## Rebuild the `.ico` assets

The transparent PNG masters live in `assets/icons/source`. To regenerate the multi-size Windows icons (16, 24, 32, 48, 64, 128, and 256 pixels):

```powershell
.\scripts\build_windows_icons.ps1
```

Native PE generation embeds the hammer-and-anvil icon resource directly. The C backend uses a Windows resource compiler (`rc.exe`) or MinGW `windres` to embed the same icon in the final executable.

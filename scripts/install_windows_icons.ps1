param([switch]$Uninstall)
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$localClasses = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Software\Classes')
$installedIconRoot = Join-Path $env:LOCALAPPDATA 'Anvil\icons'
$definitions = @(
    @{ Extension = '.ANVL'; ProgId = 'Anvil.Source'; Name = 'Anvil source code'; Icon = 'anvil-source.ico' },
    @{ Extension = '.ANVLproj'; ProgId = 'Anvil.Project'; Name = 'Anvil project'; Icon = 'anvil-project.ico' }
)

function Get-DefaultValue([string]$keyPath) {
    $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey("Software\Classes\$keyPath")
    if ($null -eq $key) { return $null }
    try { return $key.GetValue('') } finally { $key.Dispose() }
}

function Notify-Shell {
    if (-not ('Anvil.ShellChange' -as [type])) {
        Add-Type -Namespace Anvil -Name ShellChange -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("shell32.dll")]
public static extern void SHChangeNotify(int eventId, uint flags, System.IntPtr item1, System.IntPtr item2);
'@
    }
    [Anvil.ShellChange]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
}

if ($Uninstall) {
    foreach ($definition in $definitions) {
        $current = Get-DefaultValue $definition.Extension
        if ($current -eq $definition.ProgId) {
            $extensionKey = $localClasses.OpenSubKey($definition.Extension, $true)
            if ($null -ne $extensionKey) {
                try { $extensionKey.DeleteValue('', $false) } finally { $extensionKey.Dispose() }
            }
        }
        $localClasses.DeleteSubKeyTree($definition.ProgId, $false)
    }
    foreach ($iconName in @('anvil-source.ico', 'anvil-project.ico', 'anvil-executable.ico')) {
        $installedIcon = Join-Path $installedIconRoot $iconName
        if (Test-Path -LiteralPath $installedIcon) {
            Remove-Item -LiteralPath $installedIcon -Force
        }
    }
    if ((Test-Path -LiteralPath $installedIconRoot) -and
        -not (Get-ChildItem -LiteralPath $installedIconRoot -Force | Select-Object -First 1)) {
        Remove-Item -LiteralPath $installedIconRoot -Force
    }
    Notify-Shell
    Write-Output 'Removed Anvil file icons and per-user file registrations.'
    exit 0
}

$userChoiceRoot = 'Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts'
foreach ($definition in $definitions) {
    $choice = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey("$userChoiceRoot\$($definition.Extension)\UserChoice")
    if ($null -ne $choice) {
        $choice.Dispose()
        throw "Windows has a protected UserChoice association for $($definition.Extension); it was left unchanged."
    }
    $current = Get-DefaultValue $definition.Extension
    if ($current -and $current -ne $definition.ProgId) {
        throw "$($definition.Extension) already maps to '$current'; it was left unchanged."
    }
}

$codeCandidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Microsoft VS Code\Code.exe'),
    (Join-Path $env:ProgramFiles 'Microsoft VS Code\Code.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Microsoft VS Code\Code.exe')
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
if (-not $codeCandidates) {
    throw 'VS Code Code.exe was not found; no registry entries were changed.'
}
$codeExe = $codeCandidates | Select-Object -First 1

New-Item -ItemType Directory -Path $installedIconRoot -Force | Out-Null
foreach ($definition in $definitions) {
    $source = Join-Path (Join-Path $repoRoot 'assets\icons') $definition.Icon
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Required Anvil icon is missing: $source"
    }
    Copy-Item -LiteralPath $source -Destination (Join-Path $installedIconRoot $definition.Icon) -Force
}
Copy-Item -LiteralPath (Join-Path (Join-Path $repoRoot 'assets\icons') 'anvil-executable.ico') `
    -Destination (Join-Path $installedIconRoot 'anvil-executable.ico') -Force

foreach ($definition in $definitions) {
    $iconPath = Join-Path $installedIconRoot $definition.Icon
    $extensionKey = $localClasses.CreateSubKey($definition.Extension)
    try { $extensionKey.SetValue('', $definition.ProgId, [Microsoft.Win32.RegistryValueKind]::String) }
    finally { $extensionKey.Dispose() }

    $programKey = $localClasses.CreateSubKey($definition.ProgId)
    try { $programKey.SetValue('', $definition.Name, [Microsoft.Win32.RegistryValueKind]::String) }
    finally { $programKey.Dispose() }

    $iconKey = $localClasses.CreateSubKey("$($definition.ProgId)\DefaultIcon")
    try { $iconKey.SetValue('', "$iconPath,0", [Microsoft.Win32.RegistryValueKind]::String) }
    finally { $iconKey.Dispose() }

    $openKey = $localClasses.CreateSubKey("$($definition.ProgId)\shell\open\command")
    try {
        $openKey.SetValue('', "`"$codeExe`" --reuse-window `"%1`"", [Microsoft.Win32.RegistryValueKind]::String)
    } finally { $openKey.Dispose() }
}
Notify-Shell
Write-Output "Registered .ANVL and .ANVLproj icons for this Windows user; double-click opens in ${codeExe}."

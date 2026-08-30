[CmdletBinding()]
param(
    [string]$InstallRoot
)

$ErrorActionPreference = "Stop"
$version = "@VERSION@"
$bundleDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw "LOCALAPPDATA is unavailable; pass -InstallRoot with an absolute application directory."
    }
    $InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\DICOM Guide"
}

$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$installDir = Join-Path $InstallRoot $version
$binDir = Join-Path $InstallRoot "bin"
$commandPath = Join-Path $binDir "dicom-guide.cmd"

if (Test-Path -LiteralPath $installDir) {
    throw "DICOM Guide $version is already installed at $installDir"
}

New-Item -ItemType Directory -Path $installDir -Force | Out-Null
New-Item -ItemType Directory -Path $binDir -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $bundleDir "app") -Force |
    Copy-Item -Destination $installDir -Recurse -Force

$executable = Join-Path $installDir "dicom-guide.exe"
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    Remove-Item -LiteralPath $installDir -Recurse -Force
    throw "The package does not contain dicom-guide.exe"
}

$wrapper = "@echo off`r`n`"$executable`" %*`r`n"
[System.IO.File]::WriteAllText($commandPath, $wrapper, [System.Text.Encoding]::ASCII)

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$entries = @($userPath -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
if ($entries -notcontains $binDir) {
    [Environment]::SetEnvironmentVariable("Path", (($entries + $binDir) -join ";"), "User")
}
$env:Path = "$binDir;$env:Path"

& $executable --version
Write-Host "Installed DICOM Guide $version"
Write-Host "Application: $installDir"
Write-Host "Command: $commandPath"
Write-Host "Open a new terminal, then run: dicom-guide open 'C:\path\to\DICOM-folder'"

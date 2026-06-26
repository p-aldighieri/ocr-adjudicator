<#
  build_win_app.ps1 — build a self-contained, offline Windows app for OCR Adjudicator.

    tools\build_win_app.ps1 [-DatasetZip <path>] [-OutDir <path>] [-Installer] [-Run]

  Produces an app folder (OCRAdjudicator.exe + bundled .NET runtime + WebView2 + site\ =
  web build + dataset). With -Installer it also compiles OCR-Adjudicator-Setup.exe via Inno
  Setup. This is the Windows twin of tools/build_mac_app.sh: a native WebView2 window that
  serves the bundled web build + dataset from a fixed offline origin (no server, no Python).

  Defaults: DatasetZip = public\dataset.zip, OutDir = dist-win\
#>
[CmdletBinding()]
param(
  [string]$DatasetZip,
  [string]$OutDir,
  [switch]$Installer,
  [switch]$Run
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot          # repo root (parent of tools\)
Set-Location $Root

function Step($n, $msg) { Write-Host "[$n] $msg" -ForegroundColor Cyan }

# --- resolve tools ---------------------------------------------------------
$Dotnet = Join-Path $env:ProgramFiles 'dotnet\dotnet.exe'
if (-not (Test-Path $Dotnet)) {
  $cmd = Get-Command dotnet -ErrorAction SilentlyContinue
  if ($cmd) { $Dotnet = $cmd.Source } else { throw "dotnet SDK not found. Install with: winget install Microsoft.DotNet.SDK.9" }
}

if (-not $DatasetZip) { $DatasetZip = Join-Path $Root 'public\dataset.zip' }
if (-not (Test-Path $DatasetZip)) { throw "dataset zip not found: $DatasetZip" }
if (-not $OutDir) { $OutDir = Join-Path $Root 'dist-win' }

$Proj    = Join-Path $Root 'tools\win_app\OCRAdjudicator.csproj'
$IconSrc = Join-Path $Root 'tools\win_app\app.ico'
$AppDir  = Join-Path $OutDir 'app'

# --- 1. node deps: ensure the Windows native bindings are present -----------
# node_modules is often synced from the Mac via OneDrive, which leaves macOS-only native
# bindings (rolldown). Reinstall only when the Windows binding is missing.
Step '1/6' 'checking node deps (Windows native bindings)…'
if (-not (Test-Path (Join-Path $Root 'node_modules\@rolldown\binding-win32-x64-msvc'))) {
  Write-Host '      Windows rolldown binding missing — running npm install…'
  npm install
  if ($LASTEXITCODE -ne 0) { throw 'npm install failed' }
} else {
  Write-Host '      ok'
}

# --- 2. build the web app (vite leaves public/ untouched; dataset bundled below) ---
Step '2/6' 'building web app (OCR_COPY_PUBLIC=0)…'
if (Test-Path (Join-Path $Root 'dist')) { Remove-Item -Recurse -Force (Join-Path $Root 'dist') }
$env:OCR_COPY_PUBLIC = '0'
npm run build
if ($LASTEXITCODE -ne 0) { throw 'web build failed' }
if (-not (Test-Path (Join-Path $Root 'dist\index.html'))) { throw 'web build produced no dist\index.html' }

# --- 3. publish the native host (self-contained: collaborators need no .NET) ---
Step '3/6' 'publishing native WebView2 host (dotnet, self-contained win-x64)…'
if (Test-Path $AppDir) { Remove-Item -Recurse -Force $AppDir }
& $Dotnet publish $Proj -c Release -r win-x64 --self-contained true -o $AppDir
if ($LASTEXITCODE -ne 0) { throw 'dotnet publish failed' }
Copy-Item $IconSrc (Join-Path $AppDir 'app.ico') -Force   # window icon at runtime

# --- 4. bundle site = web build + unzipped dataset -------------------------
Step '4/6' 'bundling site (web build + dataset)…'
$Site = Join-Path $AppDir 'site'
if (Test-Path $Site) { Remove-Item -Recurse -Force $Site }
New-Item -ItemType Directory -Force -Path $Site | Out-Null
Copy-Item (Join-Path $Root 'dist\*') $Site -Recurse -Force
$DsDir = Join-Path $Site 'dataset'
New-Item -ItemType Directory -Force -Path $DsDir | Out-Null
Write-Host "      expanding dataset (this is the slow part)…"
Expand-Archive -Path $DatasetZip -DestinationPath $DsDir -Force
# tolerate a dataset.zip that contains a top-level dataset/ folder
if (-not (Test-Path (Join-Path $DsDir 'dataset.json')) -and (Test-Path (Join-Path $DsDir 'dataset\dataset.json'))) {
  Get-ChildItem (Join-Path $DsDir 'dataset') | Move-Item -Destination $DsDir -Force
  Remove-Item (Join-Path $DsDir 'dataset') -Recurse -Force
}
if (-not (Test-Path (Join-Path $DsDir 'dataset.json'))) { throw 'dataset.json missing after expand' }
$imgCount = (Get-ChildItem (Join-Path $DsDir 'images') -File -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host "      images bundled: $imgCount"

# --- 5. (optional) download WebView2 bootstrapper for the installer --------
$Bootstrapper = Join-Path $OutDir 'MicrosoftEdgeWebView2Setup.exe'
if ($Installer) {
  Step '5/6' 'fetching WebView2 bootstrapper (installer safety net)…'
  try {
    Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $Bootstrapper -UseBasicParsing
    Write-Host "      got $([math]::Round((Get-Item $Bootstrapper).Length/1KB)) KB"
  } catch {
    Write-Warning "could not download WebView2 bootstrapper ($_). Installer will still build; collaborators on machines without WebView2 must install it manually."
    if (Test-Path $Bootstrapper) { Remove-Item $Bootstrapper -Force }
  }
} else {
  Step '5/6' 'skipping installer (pass -Installer to build OCR-Adjudicator-Setup.exe)'
}

# --- 6. (optional) compile the installer ----------------------------------
if ($Installer) {
  Step '6/6' 'compiling installer (Inno Setup)…'
  $Iscc = @(
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')   # winget per-user install
  ) | Where-Object { Test-Path $_ } | Select-Object -First 1
  if (-not $Iscc) { throw 'ISCC.exe (Inno Setup) not found. Install with: winget install JRSoftware.InnoSetup' }
  $Iss = Join-Path $Root 'tools\win_app\installer.iss'
  $args = @("/DAppDir=$AppDir", "/DOutDir=$OutDir")
  if (Test-Path $Bootstrapper) { $args += "/DBootstrapper=$Bootstrapper" }
  & $Iscc @args $Iss
  if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compile failed' }
  Write-Host "DONE: $(Join-Path $OutDir 'OCR-Adjudicator-Setup.exe')" -ForegroundColor Green
} else {
  Write-Host "DONE (app folder): $AppDir" -ForegroundColor Green
}

if ($Run) { Start-Process (Join-Path $AppDir 'OCRAdjudicator.exe') }

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
$inc = Join-Path $root 'sdk\apps\os88api.inc'
$revision = 'd401cf8cae1c381251dbf5bfb1c995e9b01032e0'
if (-not (Test-Path $inc)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $inc) | Out-Null
    $url = "https://raw.githubusercontent.com/jggonz/os8088/$revision/apps/os88api.inc"
    Write-Host 'Fetching pinned OS8088 SDK include (one-time)...'
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $inc
    } catch {
        Write-Error "Cannot fetch OS8088 SDK. Place the matching os88api.inc in sdk\apps. $($_.Exception.Message)"
        exit 1
    }
}
$content = [System.IO.File]::ReadAllText($inc)
$checks = @(
    '(?m)^PKG_FMT\s+equ\s+10(?:\s|$)',
    '(?m)^KERNEL_SEG\s+equ\s+0x0060(?:\s|$)',
    '(?m)^%define\s+OSAPI_MENU_SET\s+KERNEL_SEG:0x011E(?:\s|$)',
    '(?m)^%define\s+OSAPI_FILE_DLG\s+KERNEL_SEG:0x0124(?:\s|$)',
    '(?m)^%define\s+OSAPI_FILE_READ\s+KERNEL_SEG:0x0109(?:\s|$)'
)
foreach ($re in $checks) {
    if ($content -notmatch $re) {
        Write-Error 'Incompatible os88api.inc: use the pinned OS8088 format-10 SDK.'
        exit 1
    }
}
Write-Host 'OS8088 format-10 SDK verified.'

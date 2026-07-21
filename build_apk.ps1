param(
    [switch]$Lite,
    [string]$OutputName = $(if ($Lite) { "poetry-app-lite-debug.apk" } else { "poetry-app-full-debug.apk" })
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$tools = Join-Path $root ".android-tools"
$jdk = Join-Path $tools "jdk-17"
$gradleHome = Join-Path $tools "gradle"
$sdk = Join-Path $tools "sdk"
$cmdlineLatest = Join-Path $sdk "cmdline-tools\latest"

$env:JAVA_HOME = $jdk
$env:ANDROID_HOME = $sdk
$env:ANDROID_SDK_ROOT = $sdk
$env:PATH = "$jdk\bin;$gradleHome\bin;$cmdlineLatest\bin;$env:PATH"

& node (Join-Path $root "build_web_bundle.js")
if ($LASTEXITCODE -ne 0) {
    throw "Web database bundle failed with exit code $LASTEXITCODE"
}

Copy-Item (Join-Path $root "index.html"), (Join-Path $root "app.js"), (Join-Path $root "style.css") -Destination (Join-Path $root "android\app\src\main\assets") -Force
if (Test-Path (Join-Path $root "android\app\src\main\assets\database")) {
    Remove-Item (Join-Path $root "android\app\src\main\assets\database") -Recurse -Force
}
$assetDatabase = Join-Path $root "android\app\src\main\assets\database"
Copy-Item (Join-Path $root "database") -Destination (Join-Path $root "android\app\src\main\assets") -Recurse -Force
if ($Lite) {
    Get-ChildItem -Path (Join-Path $assetDatabase "audio") -Recurse -Filter *.mp3 | Remove-Item -Force
}

Push-Location (Join-Path $root "android")
try {
    & gradle.bat --no-daemon clean assembleDebug
    if ($LASTEXITCODE -ne 0) {
        throw "Gradle build failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

$apk = Join-Path $root "android\app\build\outputs\apk\debug\app-debug.apk"
$out = Join-Path $root $OutputName
Copy-Item $apk $out -Force
Write-Host "APK written to $out"

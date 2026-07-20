$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$tools = Join-Path $root ".android-tools"
$downloads = Join-Path $tools "downloads"
$jdk = Join-Path $tools "jdk-17"
$gradleHome = Join-Path $tools "gradle"
$sdk = Join-Path $tools "sdk"

New-Item -ItemType Directory -Force $downloads, $tools, $sdk | Out-Null

function Download-File($url, $out) {
    if (!(Test-Path $out)) {
        Write-Host "Downloading $url"
        Invoke-WebRequest -Uri $url -OutFile $out
    }
}

function Expand-FirstChild($zip, $target) {
    $tmp = Join-Path $downloads ([IO.Path]::GetFileNameWithoutExtension($zip) + "_tmp")
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    if (Test-Path $target) { Remove-Item $target -Recurse -Force }
    Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force
    $child = Get-ChildItem $tmp | Select-Object -First 1
    Copy-Item $child.FullName $target -Recurse -Force
    Remove-Item $tmp -Recurse -Force
}

$jdkZip = Join-Path $downloads "jdk17.zip"
$gradleZip = Join-Path $downloads "gradle.zip"
$cmdlineZip = Join-Path $downloads "commandlinetools.zip"

Download-File "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse?project=jdk" $jdkZip
Download-File "https://services.gradle.org/distributions/gradle-8.9-bin.zip" $gradleZip
Download-File "https://dl.google.com/android/repository/commandlinetools-win-15859902_latest.zip" $cmdlineZip

if (!(Test-Path (Join-Path $jdk "bin\java.exe"))) {
    Expand-FirstChild $jdkZip $jdk
}

if (!(Test-Path (Join-Path $gradleHome "bin\gradle.bat"))) {
    Expand-FirstChild $gradleZip $gradleHome
}

$cmdlineLatest = Join-Path $sdk "cmdline-tools\latest"
if (!(Test-Path (Join-Path $cmdlineLatest "bin\sdkmanager.bat"))) {
    $tmp = Join-Path $downloads "cmdline_tmp"
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    Expand-Archive -LiteralPath $cmdlineZip -DestinationPath $tmp -Force
    New-Item -ItemType Directory -Force (Split-Path $cmdlineLatest) | Out-Null
    if (Test-Path $cmdlineLatest) { Remove-Item $cmdlineLatest -Recurse -Force }
    Move-Item (Join-Path $tmp "cmdline-tools") $cmdlineLatest
    Remove-Item $tmp -Recurse -Force
}

$env:JAVA_HOME = $jdk
$env:ANDROID_HOME = $sdk
$env:ANDROID_SDK_ROOT = $sdk
$env:PATH = "$jdk\bin;$gradleHome\bin;$cmdlineLatest\bin;$env:PATH"

1..20 | ForEach-Object { "y" } | sdkmanager.bat --sdk_root=$sdk --licenses
sdkmanager.bat --sdk_root=$sdk "platform-tools" "platforms;android-35" "build-tools;35.0.0"

Write-Host "Android tools ready in $tools"

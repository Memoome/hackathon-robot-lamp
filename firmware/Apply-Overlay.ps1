param([Parameter(Mandatory=$true)][string]$VendorSdkRoot)
$ErrorActionPreference='Stop'
$sdkPath=(Resolve-Path -LiteralPath $VendorSdkRoot).Path
if(-not (Test-Path -LiteralPath (Join-Path $sdkPath 'apps')) -or -not (Test-Path -LiteralPath (Join-Path $sdkPath 'qumios-dev'))){throw 'Select the WB03 SDK root containing apps and qumios-dev.'}
$overlayPath=Join-Path $PSScriptRoot 'overlay'
$backupPath=Join-Path $sdkPath ('overlay-backup-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
foreach($sourceFile in Get-ChildItem -LiteralPath $overlayPath -Recurse -File){
    $relativeName=$sourceFile.FullName.Substring($overlayPath.Length+1)
    $destinationPath=Join-Path $sdkPath $relativeName
    if(Test-Path -LiteralPath $destinationPath){
        $savedPath=Join-Path $backupPath $relativeName
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $savedPath) | Out-Null
        Copy-Item -LiteralPath $destinationPath -Destination $savedPath
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destinationPath) | Out-Null
    Copy-Item -LiteralPath $sourceFile.FullName -Destination $destinationPath
}
Write-Host "Overlay copied; originals backed up at $backupPath. Nothing built or flashed."

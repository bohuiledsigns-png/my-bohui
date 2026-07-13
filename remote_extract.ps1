# Remote extraction script - runs on target machine
$ErrorActionPreference = "Stop"
Write-Output "=== Starting extraction ==="

# Method 1: Use Python tarfile
Write-Output "Extracting with Python tarfile..."
cd D:\Bohui_Global_Push
python -c @"
import tarfile, os
f = tarfile.open('GLOWFORGE_CRM_migration.tar.gz', 'r:gz')
os.makedirs('GLOWFORGE_CRM', exist_ok=True)
f.extractall(path='GLOWFORGE_CRM')
f.close()
total = sum(len(files) for _, _, files in os.walk('GLOWFORGE_CRM'))
print(f'Extraction complete. Files: {total}')
"@

if ($LASTEXITCODE -eq 0) {
    Write-Output "Python extraction succeeded"
} else {
    Write-Output "Python extraction failed, trying 7z..."
    & "C:\Program Files\7-Zip\7z.exe" x GLOWFORGE_CRM_migration.tar.gz -oGLOWFORGE_CRM_temp -y
    & "C:\Program Files\7-Zip\7z.exe" x GLOWFORGE_CRM_temp\GLOWFORGE_CRM_migration.tar -oGLOWFORGE_CRM -y
}

# Verify key files
Write-Output "`n=== Verification ==="
if (Test-Path "D:\Bohui_Global_Push\GLOWFORGE_CRM\app.py") {
    Write-Output "[OK] app.py exists"
    $files = Get-ChildItem "D:\Bohui_Global_Push\GLOWFORGE_CRM" -Recurse -File | Measure-Object
    Write-Output "Total files extracted: $($files.Count)"
} else {
    Write-Output "[ERROR] app.py not found!"
    exit 1
}

Write-Output "`n=== Done ==="

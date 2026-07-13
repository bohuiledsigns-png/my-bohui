
$logFile = "D:\Bohui_Global_Push\install_log.txt"
"=== PIP INSTALL START at $(Get-Date) ===" | Out-File $logFile

# Upgrade pip
python -m pip install --upgrade pip -q 2>> $logFile
"pip upgraded" | Out-File $logFile -Append

# Install requirements
pip install -r D:\Bohui_Global_Push\GLOWFORGE_CRM\requirements_all.txt 2>> $logFile
$exitCode = $LASTEXITCODE
"=== PIP EXIT CODE: $exitCode ===" | Out-File $logFile -Append

# Verify key packages
python -c "import flask; print('flask:', flask.__version__)" 2>> $logFile | Out-File $logFile -Append
python -c "import playwright; print('playwright:', playwright.__version__)" 2>> $logFile -Append
python -m playwright install chromium 2>> $logFile
"=== ALL DONE at $(Get-Date) ===" | Out-File $logFile -Append

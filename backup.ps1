$src = "D:\Bohui_Global_Push\GLOWFORGE_CRM"
$date = Get-Date -Format "yyyy-MM-dd_HHmm"
$dst = "D:\Bohui_Global_Push\whatsapp上线_$date.zip"

Write-Host "Backing up $src ..."
Write-Host "To: $dst"

Add-Type -Assembly 'System.IO.Compression.FileSystem'
[System.IO.Compression.ZipFile]::CreateFromDirectory($src, $dst, 'Optimal', $false)

Write-Host "Done!"
$size = [math]::Round((Get-Item $dst).Length / 1MB, 1)
Write-Host "Size: $size MB"

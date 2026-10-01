$Host.UI.RawUI.WindowTitle = "IRCTC Telegram Agent - Launcher"

# Check if bot is already running
$existing = Get-CimInstance Win32_Process | Where-Object { 
    $_.CommandLine -and $_.CommandLine -like "*Train\main.py*" -and $_.Name -like "python*" 
}

if ($existing) {
    $existingPid = $existing[0].ProcessId
    Write-Host ""
    Write-Host "  [!] The IRCTC Bot is ALREADY RUNNING!" -ForegroundColor Yellow
    Write-Host "  Existing Process ID (PID) : " -NoNewline; Write-Host $existingPid -ForegroundColor Cyan
    Write-Host "  No new instance was created (only 1 instance allowed)." -ForegroundColor Green
    Write-Host ""
    exit 0
}

# Start single instance using pythonw.exe (windowless, silent)
$pythonExe = "C:\Users\Balaji P\AppData\Local\Programs\Python\Python313\pythonw.exe"
$mainPy = "C:\Users\Balaji P\Desktop\project\Train\main.py"
$workDir = "C:\Users\Balaji P\Desktop\project\Train"

$cmdLine = "`"$pythonExe`" `"$mainPy`""
$res = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = $cmdLine
    CurrentDirectory = $workDir
}

if ($res.ReturnValue -eq 0 -and $res.ProcessId) {
    Write-Host ""
    Write-Host "  [+] IRCTC Booking Bot started successfully!" -ForegroundColor Green
    Write-Host "  Process ID (PID)          : " -NoNewline; Write-Host $res.ProcessId -ForegroundColor Cyan
    Write-Host "  Mode                      : Silent background (pythonw.exe)" -ForegroundColor Green
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "  [X] Failed to start bot. ReturnCode: $($res.ReturnValue)" -ForegroundColor Red
    Write-Host ""
}

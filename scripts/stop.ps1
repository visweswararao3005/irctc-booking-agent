$Host.UI.RawUI.WindowTitle = "IRCTC Telegram Agent - Stopper"

$procs = Get-CimInstance Win32_Process | Where-Object { 
    $_.CommandLine -and $_.CommandLine -like "*Train\main.py*" -and $_.Name -like "python*" 
}

if ($procs) {
    foreach ($p in $procs) {
        Write-Host "  Stopping Process ID (PID): $($p.ProcessId) ($($p.Name))..." -ForegroundColor Yellow
        try {
            Stop-Process -Id $p.ProcessId -Force
            Write-Host "  [+] Process $($p.ProcessId) stopped successfully." -ForegroundColor Green
        } catch {
            Write-Host "  [X] Failed to stop process $($p.ProcessId): $_" -ForegroundColor Red
        }
    }
} else {
    Write-Host "  The IRCTC bot is not currently running." -ForegroundColor Yellow
}

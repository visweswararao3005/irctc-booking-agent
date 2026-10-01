$Host.UI.RawUI.WindowTitle = "IRCTC Telegram Agent - Status Info"

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "       IRCTC AI Booking Agent - System Status             " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Find any python process running Train\main.py
$procs = Get-CimInstance Win32_Process | Where-Object { 
    $_.CommandLine -and $_.CommandLine -like "*Train\main.py*" -and $_.Name -like "python*" 
}

if ($procs) {
    Write-Host ""
    Write-Host "  STATUS : RUNNING [ACTIVE]" -ForegroundColor Green
    Write-Host ""
    
    foreach ($p in $procs) {
        $startTime = $p.CreationDate
        if (-not $startTime) {
            try { $startTime = (Get-Process -Id $p.ProcessId).StartTime } catch {}
        }
        
        Write-Host "  Process ID (PID)  : " -NoNewline; Write-Host $p.ProcessId -ForegroundColor Yellow
        if ($startTime) {
            $uptime = (Get-Date) - $startTime
            $uptimeFormatted = "{0}d {1}h {2}m {3}s" -f $uptime.Days, $uptime.Hours, $uptime.Minutes, $uptime.Seconds
            Write-Host "  Started At        : " -NoNewline; Write-Host $startTime.ToString("yyyy-MM-dd hh:mm:ss tt") -ForegroundColor Yellow
            Write-Host "  Uptime            : " -NoNewline; Write-Host $uptimeFormatted -ForegroundColor Yellow
        }
        Write-Host "  Executable        : " -NoNewline; Write-Host $p.Name -ForegroundColor Yellow
        Write-Host "----------------------------------------------------------" -ForegroundColor DarkGray
    }
    
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host "  IRCTC Booking Agent & Scheduler are running smoothly!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "  STATUS : STOPPED [NOT RUNNING]" -ForegroundColor Red
    Write-Host ""
    Write-Host "  The IRCTC bot process is currently offline." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  To start the bot:" -ForegroundColor White
    Write-Host "  -> Double-click 'start_bot.bat' in this folder" -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Cyan
}

Write-Host ""

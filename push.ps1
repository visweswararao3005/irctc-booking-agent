$Host.UI.RawUI.WindowTitle = "IRCTC Telegram Agent - Git Push"

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "       IRCTC AI Booking Agent - Push to GitHub            " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$remoteUrl = git remote get-url origin
Write-Host "Current Remote URL: " -NoNewline; Write-Host $remoteUrl -ForegroundColor Yellow
Write-Host ""

# Check status and stage all changes
git add .
$status = git status --porcelain

if ($status) {
    $commitMsg = Read-Host "Enter commit message (or press Enter for default)"
    if (-not $commitMsg) {
        $commitMsg = "update: train booking agent enhancements"
    }
    git commit -m "$commitMsg"
} else {
    Write-Host "No uncommitted local changes." -ForegroundColor Green
}

Write-Host ""
Write-Host "Pushing to GitHub (origin main)..." -ForegroundColor Cyan
git push -u origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "  Successfully pushed to GitHub!                          " -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[!] Push failed. If the repository does not exist on GitHub yet:" -ForegroundColor Yellow
    Write-Host "  1. Go to https://github.com/new" -ForegroundColor White
    Write-Host "  2. Create a new repository named: irctc-booking-agent (or your choice)" -ForegroundColor White
    Write-Host "  3. If you used a different name, update the remote with:" -ForegroundColor White
    Write-Host "     git remote set-url origin https://github.com/visweswararao3005/<YOUR-REPO-NAME>.git" -ForegroundColor Cyan
    Write-Host "  4. Then run this script again!" -ForegroundColor Green
}
Write-Host ""

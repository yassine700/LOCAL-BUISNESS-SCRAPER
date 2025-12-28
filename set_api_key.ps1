# PowerShell script to set ScrapingBee API key
# Run this in PowerShell: .\set_api_key.ps1

$env:SCRAPINGBEE_API_KEY = "Z88OFXQ7QLCKNND13S1D7CFCR8LN6JEHKZETKXOM5HHU2B7JLLGDFM4V97R3MWUX4C54QQ8S2OBJ0ID3"
$env:SCRAPER_MODE = "high_volume"

Write-Host "API key set for current session" -ForegroundColor Green
Write-Host "Note: This is only for the current PowerShell session" -ForegroundColor Yellow
Write-Host ""
Write-Host "To make it permanent, add to .env file or Windows environment variables" -ForegroundColor Cyan


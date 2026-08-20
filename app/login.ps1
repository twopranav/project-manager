param(
    [Parameter(Mandatory=$true)][string]$Email,
    [Parameter(Mandatory=$true)][string]$Password,
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

$response = curl.exe -s -X POST "$BaseUrl/auth/login" `
    -H "Content-Type: application/x-www-form-urlencoded" `
    -d "username=$Email&password=$Password"

$parsed = $response | ConvertFrom-Json

if ($parsed.access_token) {
    $global:token = $parsed.access_token
    Write-Host "Logged in as $Email. `$token is set." -ForegroundColor Green
} else {
    Write-Host "Login failed:" -ForegroundColor Red
    Write-Host $response
}
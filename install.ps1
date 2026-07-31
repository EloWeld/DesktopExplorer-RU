# Русификатор Desktop Explorer — установка одной командой.
#
#   irm https://raw.githubusercontent.com/EloWeld/DesktopExplorer-RU/main/install.ps1 | iex
#
# Скрипт скачивает готовое приложение из последнего релиза, проверяет
# контрольную сумму и запускает мастер. После выхода из мастера файл
# удаляется — в системе ничего не остаётся ($env:DERU_KEEP=1 оставит его).

$ErrorActionPreference = 'Stop'

$Repo  = 'EloWeld/DesktopExplorer-RU'
$Base  = "https://github.com/$Repo/releases/latest/download"
$Asset = 'deru-windows-x86_64.exe'

# Не exit, а throw: через irm | iex скрипт выполняется в текущей сессии, и
# exit закрыл бы пользователю окно терминала. throw корректно проходит finally.
function Write-Dim  { param($Text) Write-Host $Text -ForegroundColor DarkGray }
function Write-Bold { param($Text) Write-Host $Text -ForegroundColor White }
function Fail       { param($Text) Write-Host "Ошибка: $Text" -ForegroundColor Red; throw $Text }

if (-not $env:OS -or $env:OS -ne 'Windows_NT') { Fail 'этот установщик рассчитан на Windows.' }

# curl.exe входит в Windows 10+, а главное — не помечает скачанный файл как
# пришедший из интернета, поэтому SmartScreen не показывает окно предупреждения.
if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) { Fail 'не найден curl.exe.' }

$Work = Join-Path ([IO.Path]::GetTempPath()) ('deru-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Work | Out-Null

try {
    Write-Bold 'Русификатор Desktop Explorer'
    Write-Dim 'Скачиваю приложение (около 80 МБ)…'
    & curl.exe -fL --progress-bar -o (Join-Path $Work $Asset) "$Base/$Asset"
    if ($LASTEXITCODE -ne 0) {
        Fail "не удалось скачать $Asset. Проверьте интернет или скачайте вручную: https://github.com/$Repo/releases/latest"
    }

    # Контрольная сумма: файл мог обрезаться на плохой связи или быть подменён
    # по дороге. SHA256SUMS лежит в том же релизе, что и приложение.
    & curl.exe -fsSL -o (Join-Path $Work 'SHA256SUMS') "$Base/SHA256SUMS"
    if ($LASTEXITCODE -ne 0) { Fail 'не удалось скачать контрольные суммы.' }
    $Line = Select-String -Path (Join-Path $Work 'SHA256SUMS') -Pattern "\b$([regex]::Escape($Asset))$" |
            Select-Object -First 1
    if (-not $Line) { Fail "в SHA256SUMS нет записи для $Asset." }
    $Expected = ($Line.Line -split '\s+')[0].ToLower()
    $Actual   = (Get-FileHash -Algorithm SHA256 (Join-Path $Work $Asset)).Hash.ToLower()
    if ($Actual -ne $Expected) {
        Fail "контрольная сумма не совпала — файл повреждён при скачивании. Попробуйте ещё раз."
    }

    Write-Dim 'Запускаю мастер установки…'
    Write-Host ''
    & (Join-Path $Work $Asset)
    $Code = $LASTEXITCODE
    Write-Host ''
    if ($Code -ne 0) { Write-Dim "Мастер завершился с кодом $Code." }
}
finally {
    if ($env:DERU_KEEP -eq '1') {
        Write-Dim "Приложение осталось здесь: $Work\$Asset"
    }
    else {
        Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
    }
}

param(
    [switch]$SkipTests,
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$taskProjectRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskProjectRoot '.venv\Scripts\python.exe'
$taskPreviousMode = [Environment]::GetEnvironmentVariable('GATEWAY_MODE', 'Process')
$taskPreviousBaseUrl = [Environment]::GetEnvironmentVariable('BASE_URL', 'Process')
$taskStackStarted = $false

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Comando falhou com codigo ${LASTEXITCODE}: $Executable $($Arguments -join ' ')"
    }
}

Push-Location $taskProjectRoot
try {
    if (-not (Test-Path -LiteralPath $taskPython)) {
        throw 'Ambiente .venv nao encontrado. Siga TESTING.md.'
    }
    if (-not $SkipTests) {
        Invoke-Checked -Executable $taskPython -Arguments @(
            '-m', 'pytest', '-q', '--cov=app', '--cov-report=term-missing',
            '--cov-fail-under=80'
        )
    }

    $env:GATEWAY_MODE = 'success'
    $env:BASE_URL = 'http://localhost:8000'
    Invoke-Checked -Executable 'docker' -Arguments @('compose', 'config', '--quiet')
    $taskUpArguments = @('compose', 'up', '-d', '--wait')
    if (-not $SkipBuild) { $taskUpArguments += '--build' }
    Invoke-Checked -Executable 'docker' -Arguments $taskUpArguments
    $taskStackStarted = $true

    $taskCases = @(
        @{ Mode = 'success'; Status = 201 },
        @{ Mode = 'fail_once'; Status = 201 },
        @{ Mode = 'always_fail'; Status = 503 },
        @{ Mode = 'timeout'; Status = 504 }
    )
    foreach ($taskCase in $taskCases) {
        $env:GATEWAY_MODE = $taskCase.Mode
        Write-Host "Validando gateway: $($taskCase.Mode) -> HTTP $($taskCase.Status)"
        if ($taskCase.Mode -ne 'success') {
            Invoke-Checked -Executable 'docker' -Arguments @(
                'compose', 'up', '-d', '--no-deps', '--force-recreate', '--wait', 'gateway'
            )
        }
        Invoke-Checked -Executable $taskPython -Arguments @(
            'scripts/validar_pagamento.py', [string]$taskCase.Status
        )
    }
    Write-Host 'Dia 1: testes, build e quatro modos validados.'
}
finally {
    try {
        if ($taskStackStarted) {
            $env:GATEWAY_MODE = 'success'
            Invoke-Checked -Executable 'docker' -Arguments @(
                'compose', 'up', '-d', '--no-deps', '--force-recreate', '--wait', 'gateway'
            )
        }
    }
    finally {
        if ($null -eq $taskPreviousMode) {
            Remove-Item Env:GATEWAY_MODE -ErrorAction SilentlyContinue
        } else {
            $env:GATEWAY_MODE = $taskPreviousMode
        }
        if ($null -eq $taskPreviousBaseUrl) {
            Remove-Item Env:BASE_URL -ErrorAction SilentlyContinue
        } else {
            $env:BASE_URL = $taskPreviousBaseUrl
        }
        Pop-Location
    }
}

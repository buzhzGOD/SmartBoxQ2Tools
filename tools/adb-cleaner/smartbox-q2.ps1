$ErrorActionPreference = 'Stop'

$python = Get-Command python -ErrorAction Stop
& $python.Source -I (Join-Path $PSScriptRoot 'src\q2_cleaner\cli.py') @args
exit $LASTEXITCODE

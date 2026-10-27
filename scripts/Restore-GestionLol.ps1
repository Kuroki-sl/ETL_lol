[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$DumpPath
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not (Test-Path -LiteralPath $DumpPath -PathType Leaf)) {
    throw "No se encontró el respaldo: $DumpPath"
}
$resolvedDumpPath = (Resolve-Path -LiteralPath $DumpPath).Path

$containerId = $null
$containerArchivePath = "/tmp/gestion_lol_restore_{0}.dump" -f [guid]::NewGuid().ToString("N")
Push-Location $repoRoot
try {
    $containerIdOutput = docker compose ps -q lol-postgres
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo consultar Docker Compose. Comprueba que Docker Desktop esté iniciado."
    }
    $containerId = [string]$containerIdOutput
    $containerId = $containerId.Trim()
    if (-not $containerId) {
        throw "El servicio lol-postgres no está activo. Inícialo con: docker compose up -d lol-postgres"
    }

    $confirmation = Read-Host "Esto reemplazará gestion_lol en ESTE computador. Escribe REEMPLAZAR para continuar"
    if ($confirmation -cne "REEMPLAZAR") {
        throw "Restauración cancelada; la base local no fue modificada."
    }

    docker cp $resolvedDumpPath "${containerId}:$containerArchivePath"
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo copiar el archivo de respaldo al contenedor."
    }

    docker compose exec -T lol-postgres pg_restore `
        -U postgres `
        -d gestion_lol `
        --clean `
        --if-exists `
        --no-owner `
        --no-privileges `
        --exit-on-error `
        $containerArchivePath
    if ($LASTEXITCODE -ne 0) {
        throw "Falló pg_restore. Revisa el archivo y el estado del contenedor; la base podría haber quedado parcialmente restaurada."
    }

    Write-Output "Respaldo restaurado en gestion_lol."
} finally {
    if ($containerId) {
        try {
            docker compose exec -T lol-postgres rm -f $containerArchivePath *> $null
        } catch {
            # No ocultar el resultado de la restauración por fallar al limpiar el temporal.
        }
    }
    Pop-Location
}

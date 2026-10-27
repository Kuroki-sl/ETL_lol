[CmdletBinding()]
param(
    [string]$BackupDirectory = "backups"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if ([System.IO.Path]::IsPathRooted($BackupDirectory)) {
    $backupDirectoryPath = $BackupDirectory
} else {
    $backupDirectoryPath = Join-Path $repoRoot $BackupDirectory
}

New-Item -ItemType Directory -Path $backupDirectoryPath -Force | Out-Null

$containerId = $null
$containerArchivePath = $null
$archivePath = $null
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

    $archiveName = "gestion_lol_{0}.dump" -f (Get-Date -Format "yyyyMMdd_HHmmss_fff")
    $containerArchivePath = "/tmp/$archiveName"
    $archivePath = Join-Path $backupDirectoryPath $archiveName

    docker compose exec -T lol-postgres pg_dump `
        -U postgres `
        -d gestion_lol `
        --format=custom `
        --no-owner `
        --no-privileges `
        --file $containerArchivePath
    if ($LASTEXITCODE -ne 0) {
        throw "Falló pg_dump; no se creó el respaldo."
    }

    docker cp "${containerId}:$containerArchivePath" $archivePath
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo copiar el respaldo desde el contenedor."
    }

    Write-Output "Respaldo creado: $archivePath"
} finally {
    if ($containerId -and $containerArchivePath) {
        try {
            docker compose exec -T lol-postgres rm -f $containerArchivePath *> $null
        } catch {
            # El respaldo del host ya fue copiado; no fallar por limpiar el temporal.
        }
    }
    Pop-Location
}

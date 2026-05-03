param([string]$Target = "help")

$COMPOSE = "docker compose -f infra/docker-compose.yml"
$COMPOSE_OMRS = "docker compose -f infra/docker-compose.openmrs.yml"
$PYTHON = if (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { "python" }

switch ($Target) {
    "up"           { Invoke-Expression "$COMPOSE up -d" }
    "down"         { Invoke-Expression "$COMPOSE down" }
    "logs"         { Invoke-Expression "$COMPOSE logs -f" }
    "status"       { Invoke-Expression "$COMPOSE ps" }
    "openmrs-up"   { Invoke-Expression "$COMPOSE_OMRS up -d" }
    "openmrs-down" { Invoke-Expression "$COMPOSE_OMRS down" }
    "seed"         { bash scripts/seed.sh }
    "demo"         { Invoke-Expression "$PYTHON scripts/run-demo.py" }
    "reset"        { bash scripts/reset-demo.sh }
    "help" {
        Write-Host "Usage: .\scripts\make.ps1 <target>"
        Write-Host ""
        Write-Host "Targets:"
        Write-Host "  up           - start full stack"
        Write-Host "  down         - stop full stack"
        Write-Host "  logs         - tail all logs"
        Write-Host "  status       - show container status"
        Write-Host "  openmrs-up   - start OpenMRS only"
        Write-Host "  openmrs-down - stop OpenMRS only"
        Write-Host "  seed         - generate and load synthetic data (phase 1+)"
        Write-Host "  demo         - run the demo pipeline (phase 2+)"
        Write-Host "  reset        - wipe and reseed (phase 1+)"
    }
    default {
        Write-Host "Unknown target: $Target"
        Write-Host "Run .\scripts\make.ps1 help for options."
    }
}

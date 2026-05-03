#!/usr/bin/env bash
# Orchestrates Phase 1 data pipeline:
#   1. Generate Synthea patients (FHIR R4)
#   2. Apply Kenyan localization
#   3. Generate CHW activity overlay
#   4. Bulk-load into OpenMRS
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Verify Java 11+
JAVA_VERSION=$(java -version 2>&1 | awk -F '"' '/version/ {print $2}' | cut -d'.' -f1)
if [ -z "${JAVA_VERSION}" ] || [ "${JAVA_VERSION}" -lt 11 ] 2>/dev/null; then
    echo "Java 11+ required. Detected: $(java -version 2>&1 | head -1)"
    echo "Install: winget install Microsoft.OpenJDK.21"
    exit 1
fi
echo "Java OK (version ${JAVA_VERSION})"

# Verify Python 3
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "Python 3 not found."
    exit 1
fi
PYTHON=$(command -v python3 || command -v python)
echo "Python OK (${PYTHON})"

echo ""
echo "=== Step 1: Synthea ==="
bash "${ROOT_DIR}/data/synthea/generate.sh"

echo ""
echo "=== Step 2: Kenyan Localization ==="
"${PYTHON}" "${ROOT_DIR}/data/synthea/kenyan-localization/localize.py"

echo ""
echo "=== Step 3: CHW Activity Overlay ==="
"${PYTHON}" "${ROOT_DIR}/data/chw_overlay/generate_chw_activity.py"

echo ""
echo "=== Step 4: Load to OpenMRS ==="
"${PYTHON}" "${ROOT_DIR}/data/load_to_openmrs.py"

echo ""
echo "=== Seed complete ==="

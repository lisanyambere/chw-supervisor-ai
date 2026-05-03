#!/usr/bin/env bash
# Downloads Synthea JAR and generates ~500 patients with FHIR R4 output.
set -e

# Prefer JAVA_HOME if set (winget installs to Program Files\Microsoft\jdk-*)
if [ -n "${JAVA_HOME}" ]; then
    JAVA="${JAVA_HOME}/bin/java"
else
    JAVA="java"
fi

SYNTHEA_JAR="synthea-with-dependencies.jar"
SYNTHEA_URL="https://github.com/synthetichealth/synthea/releases/download/master-branch-latest/${SYNTHEA_JAR}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/output"

if [ ! -f "${SCRIPT_DIR}/${SYNTHEA_JAR}" ]; then
    echo "Downloading Synthea..."
    curl -L -o "${SCRIPT_DIR}/${SYNTHEA_JAR}" "${SYNTHEA_URL}"
fi

mkdir -p "${OUTPUT_DIR}"

# Run with seed 42 for reproducibility. Massachusetts used as base state — all
# names/addresses are replaced in the localization step.
echo "Generating 500 patients (seed=42, this takes 3-5 minutes)..."
"${JAVA}" -jar "${SCRIPT_DIR}/${SYNTHEA_JAR}" \
    -p 500 \
    -s 42 \
    --exporter.baseDirectory="${OUTPUT_DIR}/" \
    --exporter.fhir.export=true \
    --exporter.hospital.fhir.export=false \
    --exporter.practitioner.fhir.export=false \
    --exporter.fhir.use_us_core_ig=false \
    --exporter.years_of_history=2 \
    Massachusetts

echo "Done. FHIR bundles written to ${OUTPUT_DIR}/fhir/"
ls "${OUTPUT_DIR}/fhir/" | wc -l | xargs echo "Bundles generated:"

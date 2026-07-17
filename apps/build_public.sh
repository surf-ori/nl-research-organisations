#!/usr/bin/env bash
# Populate apps/public/ from the committed data/ and assets/ directories.
# Run before exporting apps/dashboard.py to WASM (locally or in CI) so the
# read-only app has the files it serves via mo.notebook_location() / "public".
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf apps/public
mkdir -p apps/public/curated apps/public/assets apps/public/raw

cp data/curated/*.csv apps/public/curated/
cp data/nl_research_orgs.parquet apps/public/nl_research_orgs.parquet
cp assets/surf-logo.svg apps/public/assets/surf-logo.svg

for stage in ror zenodo openalex openaire alei pic barcelona memberships nbn; do
  if [ -f "data/raw/$stage/_metadata.json" ]; then
    mkdir -p "apps/public/raw/$stage"
    cp "data/raw/$stage/_metadata.json" "apps/public/raw/$stage/_metadata.json"
  fi
done
if [ -f data/raw/_assembly_metadata.json ]; then
  cp data/raw/_assembly_metadata.json apps/public/raw/_assembly_metadata.json
fi

echo "apps/public/ ready"

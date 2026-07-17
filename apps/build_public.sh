#!/usr/bin/env bash
# Populate apps/public/ from the committed data/ and assets/ directories.
# Run before exporting apps/dashboard.py to WASM (locally or in CI) so the
# read-only app has the files it serves via mo.notebook_location() / "public".
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf apps/public
mkdir -p apps/public/curated apps/public/assets

cp data/curated/*.csv apps/public/curated/
cp data/nl_research_orgs.parquet apps/public/nl_research_orgs.parquet
cp assets/surf-logo.svg apps/public/assets/surf-logo.svg
cp -r data/raw apps/public/raw

uv run apps/prepare_raw_previews.py

echo "apps/public/ ready"

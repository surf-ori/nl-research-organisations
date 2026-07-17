#!/usr/bin/env bash
# Populate apps/public/ from the committed data/ and assets/ directories.
# Run before exporting apps/dashboard.py to WASM (locally or in CI) so the
# read-only app has the files it serves via mo.notebook_location() / "public".
#
# data/raw/ is gitignored (bronze, too big/slow to commit) and not copied here —
# data/processed/ (silver, built locally by src/processor.py and committed) is
# what the published app actually reads.
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf apps/public
mkdir -p apps/public/curated apps/public/processed apps/public/assets

cp data/curated/*.csv apps/public/curated/
cp data/processed/*.parquet apps/public/processed/
cp data/nl_research_orgs.parquet apps/public/nl_research_orgs.parquet
cp assets/surf-logo.svg apps/public/assets/surf-logo.svg

echo "apps/public/ ready"

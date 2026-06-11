# Public Document Corpus Collector

This directory stores the collector for public HWPX/HWP samples. Do not commit
downloaded source documents here.

Recommended workflow:

```bash
python3 tests/fixtures/public_document_corpus/fetch_corpus.py \
  --url "https://www.korea.kr/..." \
  --url "https://opengov.seoul.go.kr/..." \
  --manifest tests/fixtures/public_document_corpus/manifest.local.json
```

The collector discovers `.hwpx` and `.hwp` links from seed pages, records URL
metadata and SHA-256 when downloads are enabled, and refuses to overwrite
baseline manifests unless `--force` is passed. Commit only scripts and curated
manifests that contain URLs and hashes, not the original documents.

Baseline files named `baseline*.json` are append-only evidence. Create a new
baseline version when scoring rules change.

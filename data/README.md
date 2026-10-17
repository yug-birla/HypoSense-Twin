# data/

Patient-level records are **never committed**. Only the manifests (`MANIFEST.json`, `MANIFEST.sha256`) are version-controlled.

| Path | Contents | Committed |
|---|---|---|
| `raw/downloads/` | figshare archives v5 (canonical), v2 and v1 (reconciliation only), each with a `.provenance.json` sidecar | No |
| `raw/ShanghaiT2DM/` | Allow-listed extraction of v5: `Shanghai_T2DM/` (109 workbooks), `Shanghai_T2DM_Summary.xlsx`, `note.txt` | No |
| `raw/reconciliation/v1, v2/` | Extractions of earlier versions, used only to explain blueprint differences | No |
| `MANIFEST.json`, `MANIFEST.sha256` | SHA-256 of every file in `raw/ShanghaiT2DM/` (111 files). `load_dataset` refuses to run on a mismatch | **Yes** |
| `processed/` | Derived Parquet tables, regenerated deterministically from `raw/` | No |

Reproduce from scratch:
```bash
uv run hyposense data fetch                 # canonical v5 (MD5 + SHA-256 verified)
uv run hyposense data fetch --version 2     # reconciliation copies (optional)
uv run hyposense data fetch --version 1
uv run hyposense data extract
uv run hyposense data manifest              # verify against the committed manifest
uv run hyposense audit run                  # structural audit + G0/G1
```

## Rules

- Raw files are read-only. Never edit, clean or re-save them in place.
- Use the **official figshare copy**. Do not use the GitHub mirror audited in the blueprint
  (the mirror equals figshare v1–v4; v5 adds the 188 rows documented in its `note.txt`, ADR-017).
- Sealed evaluation partition (E): before the protocol freeze, only automated aggregate-only
  integrity checks may touch E files (approved P-C5). Modelling code must use
  `load_dataset(AccessScope.TUNING_ONLY)` (ADR-018).
- Licence: CC BY 4.0. Attribute Zhao et al., *Scientific Data* 2023, doi:10.1038/s41597-023-01940-7.

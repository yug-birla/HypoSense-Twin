# data/

Patient-level records are **never committed**. Only `MANIFEST.sha256` is version-controlled.

| Path | Contents | Committed |
|---|---|---|
| `raw/` | Official ShanghaiT2DM copy from figshare (doi:10.6084/m9.figshare.c.6310860), unmodified and read-only | No |
| `MANIFEST.sha256` | SHA-256 of every raw file. The loader refuses to run on a mismatch (Blueprint §10.1) | Yes (created in S1) |
| `processed/` | Derived Parquet tables, regenerated deterministically from `raw/` | No |

## Rules

- Raw files are read-only. Never edit, clean or re-save them in place.
- Use the **official figshare copy**. Do not use the GitHub mirror audited in the blueprint
  (Gate G0: the mirror has 188 fewer CGM readings than the published total).
- Sealed evaluation partition (E): before the protocol freeze, no CGM values, labels, outcomes
  or model outputs of E patients may be examined. Permitted outcome-blind uses are pending
  approval (docs/PROPOSALS.md, P-C5).
- Licence: CC BY 4.0. Attribute Zhao et al., *Scientific Data* 2023, doi:10.1038/s41597-023-01940-7.

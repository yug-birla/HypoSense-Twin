"""One-off import of the blueprint author's original T/E partition (P-C4, option A).

Usage:
    uv run python scripts/import_original_partition.py <bundle>/audit_outputs/partition.csv \
        [<bundle zip>]

Steps:
1. Hash the source file (and the bundle zip, if given).
2. Verify that `reproduce_audit2_split` (seed 2026, frac_T 0.30) reproduces the source's
   `partition` column exactly from its `stratum` column. On any mismatch the import is
   refused.
3. Write configs/partition.csv with columns (patient_id, partition) ONLY. Per-patient episode
   counts and strata of sealed E patients are deliberately NOT copied into the repository (P-C5).
4. Write configs/partition.provenance.json (hashes, algorithm, verification, aggregate counts).

After import, pin the printed SHA-256 in configs/default.yaml `partition.sha256`.
The partition must never be regenerated or edited afterwards (ADR-016).
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

from hyposense.common.config import REPO_ROOT
from hyposense.common.hashing import sha256_file
from hyposense.common.provenance import utc_now_iso
from hyposense.data.partition import reproduce_audit2_split

SEED, FRAC_T = 2026, 0.30


def main() -> int:
    src = Path(sys.argv[1])
    bundle = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    with src.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    strata = {r["pid"].strip(): int(r["stratum"]) for r in rows}
    original = {r["pid"].strip(): r["partition"].strip() for r in rows}
    reproduced = reproduce_audit2_split(strata, SEED, FRAC_T)
    mismatches = sorted(p for p in original if original[p] != reproduced[p])
    if mismatches or len(original) != len(rows):
        print(f"REFUSED: algorithm does not reproduce source ({len(mismatches)} mismatches)")
        return 1

    out_csv = REPO_ROOT / "configs" / "partition.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["patient_id", "partition"])
        for pid in sorted(original):
            w.writerow([pid, original[pid]])
    digest = sha256_file(out_csv)

    by_stratum = Counter(strata.values())
    t_by_stratum = Counter(strata[p] for p, v in original.items() if v == "T")
    provenance = {
        "partition_version": "1.0.0",
        "status": "OFFICIAL PROJECT SPLIT — immutable (ADR-016)",
        "imported_utc": utc_now_iso(),
        "origin": "Blueprint v2.0 feasibility audit (audit2.py), run by the blueprint author on a "
        "GitHub mirror of ShanghaiT2DM (pre-2023-10-26 content)",
        "source_file": {"name": "audit_outputs/partition.csv", "sha256": sha256_file(src)},
        "source_bundle": ({"name": bundle.name, "sha256": sha256_file(bundle)} if bundle else None),
        "algorithm": {
            "description": "stratify by treated*2 + has_L1; within ascending stratum, sort patient "
            "ids as strings, shuffle with one shared numpy Generator, first "
            "int(round(frac_T*n)) -> T",
            "implementation": "hyposense.data.partition.reproduce_audit2_split",
            "seed": SEED,
            "frac_T": FRAC_T,
            "strata_definition": {
                "0": "untreated, no L1",
                "1": "untreated, >=1 L1",
                "2": "treated, no L1",
                "3": "treated, >=1 L1",
            },
        },
        "verification": {
            "algorithm_reproduces_source": True,
            "mismatches": 0,
            "numpy_version_used_for_verification": __import__("numpy").__version__,
        },
        "counts": {
            "patients": len(original),
            "T": sum(v == "T" for v in original.values()),
            "E": sum(v == "E" for v in original.values()),
            "stratum_sizes": {str(k): by_stratum[k] for k in sorted(by_stratum)},
            "T_per_stratum": {str(k): t_by_stratum[k] for k in sorted(by_stratum)},
        },
        "known_caveats": [
            "Strata (treated, has-L1) were computed by the original audit on mirror data. "
            "figshare v5 adds rows to recordings 2003_0 and 2029_0, so the has-L1 stratum of "
            "patients 2003 and 2029 must be re-checked in S2. A stratum change would not "
            "invalidate the split (stratification only balances the partition), but it must be "
            "reported.",
            "The treated flag is re-verified against the production medication parser in S3.",
        ],
        "output": {
            "file": "configs/partition.csv",
            "sha256": digest,
            "columns": ["patient_id", "partition"],
        },
    }
    (REPO_ROOT / "configs" / "partition.provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    print(f"imported {len(original)} patients; configs/partition.csv sha256 = {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

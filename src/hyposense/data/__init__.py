"""Data adapter and validator: harmonise ShanghaiT2DM column variants, parse units and timestamps,
emit typed events and quality flags. Blueprint 9.1, 10.1, 25.3 (load_recording). Also hosts the
partition guard that blocks sealed-partition (E) access before freeze.

Status: NOT IMPLEMENTED (planned for S1-S2). See docs/ARCHITECTURE.md.
"""

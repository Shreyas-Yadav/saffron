# Nangate45 Open Cell Library

`nangate45_typ.lib.gz` is the **typical-corner** Liberty timing model from the
NangateOpenCellLibrary (a free, open 45nm standard-cell library, © 2004–2011
Nangate Inc., all rights reserved for the original; redistributed openly and widely
used for academic/EDA tooling — it ships with OpenSTA's own `examples/`).

We use it only to give yosys' `abc` a real cell library to map onto and to give
OpenSTA realistic gate delays/areas, so Saffron can report a representative max
frequency, critical path, and area. It is **not** a manufacturing PDK.

Stored gzipped (≈1.3 MB vs ≈6.7 MB) and decompressed into a scratch workspace at
analysis time. Extracted from the `openroad/opensta` Docker image
(`/OpenSTA/examples/nangate45_typ.lib.gz`).

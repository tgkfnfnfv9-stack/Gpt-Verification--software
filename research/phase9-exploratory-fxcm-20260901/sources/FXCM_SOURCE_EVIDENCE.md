# FXCM source evidence

Metadata frozen on `2026-09-01` before price access.

- Repository: `https://github.com/fxcm/MarketData`
- Pinned master head: `924393dd545fab187527d95ef8b1178284b274b6`
- Pinned head role: documentation and URL-contract evidence only
- Live dataset release version: unpublished/unversioned endpoint objects
- README SHA-256: `898bdda886b26efee50f4219f02d3264e9e57d71e91f76d4f6765a599b9d7aa6`
- Official pandas example SHA-256: `2a34f14d16c6635dfa82fa61fcbbf0c346cfd9f4b2f46fa60f6e4f56120fde3d`

The pinned README identifies H1 CandleData as a free sample, publishes the
`https://candledata.fxcorporate.com/{periodicity}/{instrument}/{year}/{week}.csv.gz`
template, lists 2017--2020 and the supported FX instruments, states UTC, and
links provider-authored Python examples. The pandas example loops over the URL
template with `pandas.read_csv`. This is explicit automated access evidence.

The repository head is not a version identifier for the live CandleData
objects. Reproducibility is established by recording SHA-256 and byte count for
each of the 832 downloaded objects in the same-run inventory.

FXCM describes the data points as indicative and based on the lowest spreads
available to Active Trader accounts. The README states UTC but does not
explicitly define the row timestamp as `BAR_OPEN`; that interpretation remains
an exploratory assumption and is not a Formal provider-semantic claim.

The README also limits use to personal use under the linked FXCM EULA:
`https://www.fxcm.com/uk/forms/eula/`. The workflow therefore requires a second
exact dispatch confirmation for personal, non-commercial use and EULA
acceptance. The agent cannot supply that confirmation on the user's behalf.

The same README limits CandleData to 21 FX pairs. It is not evidence for metals,
energy, M15, an independent provider schedule, a versioned release calendar or
raw-data redistribution. Raw price files therefore remain ephemeral.

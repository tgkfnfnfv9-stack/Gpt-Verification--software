# Dukascopy commodity source evidence (price-free)

Recorded 2026-09-03. This file records public documentation and pinned local
runtime metadata only. It contains no price request, price row, authenticated
session result, or Drive access.

## Provider and source version

- Provider: Dukascopy Bank SA.
- Interface: authenticated JForex API historical bars.
- DDS2 client: `3.6.51`.
- API: `2.13.99`.
- Existing pinned POM SHA-256:
  `ea80b6e0c938ca4831d723f29ec2ca311967788b00c6218c6768b91cbdb28bd9`.
- Existing pinned root JAR SHA-256:
  `daf2d98cded0a8ff85276965f0c10eb01692acff7949a5898ab295708e2c26c2`.
- Existing pinned SDK ZIP SHA-256:
  `a7a2fb6c070f800145adf5d88a7de9ed37e7544878b12b4312ea006365947016`.
- The historical dataset itself has no documented immutable release identifier.
  Reproducibility therefore also requires request identity, response SHA-256,
  canonical CSV SHA-256, timestamp SHA-256, and retrieval provenance.

## Official documentation

- JForex API overview: <https://www.dukascopy.com/swiss/english/forex/api/jforex-api/>
- JForex API EULA: <https://www.dukascopy.com/swiss/docs/api/index.php>
- `IHistory` API: <https://www.dukascopy.com/client/javadoc3/com/dukascopy/api/IHistory.html>
- Historical data exporter: <https://www.dukascopy.com/swiss/english/marketwatch/historical/>
- Trading hours and metals: <https://www.dukascopy.com/swiss/english/forex/forex-trading-accounts/link/>
- CFD market hours: <https://www.dukascopy.com/swiss/english/cfd/range-of-markets/>
- CFD monthly adjustment explanation: <https://www.dukascopy.com/swiss/english/cfd/cfd-monthly-adjustment/>
- CFD adjustment calendar: <https://www.dukascopy.com/swiss/english/marketwatch/calendars/cfd-price-adjustment-calendar/>

## Fixed mapping and API semantics

| Canonical | JForex instrument | Direct periods | Offer sides |
|---|---|---|---|
| XAUUSD | `XAU/USD` | `ONE_MIN`, `ONE_HOUR` | `BID`, `ASK` |
| XAGUSD | `XAG/USD` | `ONE_MIN`, `ONE_HOUR` | `BID`, `ASK` |
| BRENTCMDUSD | `BRENT.CMD/USD` | `ONE_MIN`, `ONE_HOUR` | `BID`, `ASK` |
| LIGHTCMDUSD | `LIGHT.CMD/USD` | `ONE_MIN`, `ONE_HOUR` | `BID`, `ASK` |

The adapter must resolve each exact string through `Instrument.fromString` and
fail closed if the returned instrument differs. Deprecated energy constants are
not accepted. Timestamps are normalized as UTC bar-open instants. The API's end
bar time is inclusive, while the acquisition contract is half-open.

## Hours and roll evidence boundary

Current published templates indicate weekday trading with daily maintenance
breaks. Metals use Sunday-to-Friday schedules whose displayed GMT hour changes
with daylight saving; BRENT and LIGHT have different daily sessions, and energy
roll-adjustment days start their break 20 minutes early. These are current
templates, not a complete historical calendar for 2012–2025.

The provider describes the energy instruments as non-expiring spot-traded CFDs
whose prices are influenced by current futures and switched to the next futures
contract. Therefore the proposed canonical series preserves provider quotes and
does not construct, back-adjust, or ratio-adjust a local futures continuous
series. Exact historical switch dates, old/new underlying contracts, and
provider adjustments are required as separate versioned metadata before
completeness can pass.

## License precondition

The JForex EULA states personal/non-commercial use constraints, restricts
third-party distribution/public use, requires Dukascopy attribution, and states
that a user consulting price quotes agrees to arrange and use a simultaneous
alternative market-data source. This preaudit does not decide legal compliance.
The repository owner must confirm the intended use, Vault access boundary,
attribution, and alternative-source arrangement or obtain written provider
clarification before acquisition.

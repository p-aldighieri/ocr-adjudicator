# One-shot data-repair passes (historical)

These scripts each ran ONCE against public/dataset/dataset.json and the preserved-adjudications
JSON, then shipped. They are kept for provenance (they encode the data decisions made in each
repair round), not for re-use.

- apply_pass1_fixes.py  (2026-06-23) - fixed 12 wrong-page/row records from the PI's first
  adjudication pass (former-name mismatches: Auburn, Arizona State, Baylor, Boston College);
  Baruch marked part-of-CCNY.
- apply_pass2_fixes.py  (2026-07-29) - repaired the 288 wrong_page items from the RA's full
  first pass: 218 page splices, 74 absent-by-design N/As, state fixes (Jackson State, Williams),
  income corrections; reset 217 items for re-adjudication.
- apply_pass3_reopen.py (2026-07-29) - reopen round from the flagged-cell audit: 68 items /
  127 cells reopened (blind disputed incomes, verified-value confirms, 44 joint-faculty
  conversions), units reverted to as-printed. The later wave-2 row-number repair (137 n fixes,
  15 value corrections, page re-bundles incl. Akron 1959) was applied by session scripts and is
  documented in the project records.

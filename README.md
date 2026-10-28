# FRE-GY-9743-Assignments-2026fall
Assignments for NYU, FRE-GY 9743, Fall 2026.

## Assignment 6 submission: Raj Pawar (`Raj_Pawar_Branch`)

| Deliverable | Location |
|---|---|
| TODO 1 and 2: `ProductRFRSwap` builds its fixed and compounded-overnight legs, `ProductOvernightIndexBasisSwap` builds its two overnight legs with the spread on leg 1 only, both through the supplied `InterestRateStream` (schedules on the index's fixing calendar, payments on the swap's payment terms) | `fixedincomelib/product/linear_products.py` |
| TODO 3 and 4: `ProductFactory.create_rfr_swap` and `create_overnight_index_basis_swap` read the convention (index or indices, accrual basis and periods, payment offset and conventions, compounding) and the swap date rule for `axis1` (`1Y` spot start, `3Mx1Y` forward start, explicit dates); the quote is the fixed rate or the leg-1 spread | `fixedincomelib/product/product_factory.py` |
| TODO 5 and 6: `ValuationEngineProductRfrSwap.calculate_value` and `ValuationEngineProductOvernightIndexBasisSwap.calculate_value` combine the supplied leg engines with their signs into `value_` and `cash_` | `fixedincomelib/yield_curve/valuation_engine.py` |
| Professor's notebook executed top to bottom with the six TODOs in place (no notebook cell needed changing); every `assert` in it passes | `hw6_interest_rate_products.ipynb` |
| Tests: leg construction (dates, calendars that differ on Good Friday, periods, spread, compounding, serialization, display), the factory's convention mapping and `axis1` rules, and the engines against a hand calculation (telescoped compounded rates, leg PVs, par rate and fair spread, arithmetic compounding, same-day and mid-life cash from fixings, past payments, reports, registry dispatch, the supplied FRA) | `tests/test_interest_rate_products.py`, `tests/test_swap_valuation_engines.py` |
| Write-up: Part I (EUR/USD forward collateralised in GBP: valuation formula, fair strike, which discount factors suffice) and a summary of Part II | `writeup/Assignment6_Writeup_RajPawar.pdf` (source `.tex` alongside) |
| Project page, numbers generated from the library | `docs/index.html` (built by `docs/build_page.py`) |

### How to run

```bash
pip install -r requirements.txt                       # Python 3.11, QuantLib 1.41
jupyter notebook hw6_interest_rate_products.ipynb     # Run All
python tests/test_interest_rate_products.py           # or, with pytest installed: python -m pytest tests -q
python tests/test_swap_valuation_engines.py
```

Within `fixedincomelib/` only the three `TODO` files changed; everything else on the branch (notebook outputs, tests, write-up, docs page) is listed in the table above. Besides the six `TODO` bodies I added two small private helpers: `ProductOvernightIndexBasisSwap._overnight_leg` (one compounded leg on the swap's dates and payment terms, used for both legs of the basis swap) and `ProductFactory._swap_dates` (the `axis1` date rule shared by the two swap builders). The FRA example, the streams, the model, data, report and API layers are unchanged.

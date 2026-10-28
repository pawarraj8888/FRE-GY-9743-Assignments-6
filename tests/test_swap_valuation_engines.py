"""Checks for ValuationEngineProductRfrSwap and ValuationEngineProductOvernightIndexBasisSwap
(fixedincomelib/yield_curve/valuation_engine.py).

    python tests/test_swap_valuation_engines.py    # plain runner
    python -m pytest tests -q                      # with pytest

The model and the trades are the ones in hw6_interest_rate_products.ipynb. The reference numbers are
worked out here without the library (QuantLib is used only for the business-day calendars): discount factors
from the piecewise-constant forward rates
(D = exp(-integral f), each node's rate applying on the bucket that ends at the node), ACT/360 accruals
from day counts, and the compounded overnight rate from the projection curve. Daily compounding of
projected overnight rates telescopes, (prod_j D(s_j)/D(e_j)) - 1 = D(T_s)/D(T_e) - 1, because every
observation period of the index calendar lies inside the coupon, so a compounded coupon pays
N (D(T_s)/D(T_e) - 1) plus N alpha s for the spread, discounted with the funding curve.
"""
import datetime as dt
import math
import os
import sys

import pandas as pd
import QuantLib as ql

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
for path in (REPO_ROOT, TESTS_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from fixedincomelib import (  # noqa: E402
    qfCreateBuildMethod, qfCreateCashflowsReport, qfCreateData1D, qfCreateDataCollection, qfCreateModel,
    qfCreateModelBuildMethodCollection, qfCreateProductFRA, qfCreateProductFromDataConvention,
    qfCreateValuationParameters, qfCreateValuationParametersCollection, qfCreateValueReport,
)
from fixedincomelib.date import Date  # noqa: E402
from fixedincomelib.market.registries import IndexFixingsManager  # noqa: E402
from fixedincomelib.valuation import ValuationEngineProductRegistry, ValuationRequest  # noqa: E402
from fixedincomelib.yield_curve.valuation_engine import (  # noqa: E402
    ValuationEngineInterestRateStream, ValuationEngineProductFra, ValuationEngineProductOvernightIndexBasisSwap,
    ValuationEngineProductRfrSwap,
)
from test_interest_rate_products import (  # noqa: E402
    ANNUAL, BASIS_CONVENTION, BASIS_SPREAD, EFFECTIVE_DATE, END_DATE, FIXED_RATE, NOTIONAL, QUARTERLY,
    SWAP_CONVENTION, VALUE_DATE, make_basis_swap, make_swap,
)

FUNDING_INDEX = "SOFR-1B-FLAT"
SOFR_IFR = [("2026-04-02", 0.03), ("2027-01-04", 0.04), ("2028-01-03", 0.05)]
FF_IFR = [("2026-07-02", 0.028), ("2028-01-03", 0.037)]
SPREAD_IFR = [("2026-07-02", 0.0), ("2028-01-03", 0.001)]
TOL = 1e-6


def build(value_date=VALUE_DATE, sofr=SOFR_IFR, fed_funds=FF_IFR, spread=SPREAD_IFR):
    """The notebook's three-component model: SOFR-1B, FF-1B and SOFR-1B-FLAT as a spread over SOFR."""
    def frame(nodes):
        return pd.DataFrame({"values": [v for _, v in nodes]}, index=pd.Index([d for d, _ in nodes], name="Node date"))
    data = qfCreateDataCollection([
        qfCreateData1D("INSTANTANEOUS FORWARD RATE", "SOFR-1B-IFR", frame(sofr)),
        qfCreateData1D("INSTANTANEOUS FORWARD RATE", "FF-1B-IFR", frame(fed_funds)),
        qfCreateData1D("INSTANTANEOUS FORWARD RATE", "SOFR-1B-FUNDING-IFR", frame(spread)),
    ])
    methods = qfCreateModelBuildMethodCollection([
        qfCreateBuildMethod("YIELD_CURVE_INDEX", {"TARGET": "SOFR-1B", "INSTANTANEOUS FORWARD RATE": "SOFR-1B-IFR"}),
        qfCreateBuildMethod("YIELD_CURVE_INDEX", {"TARGET": "FF-1B", "INSTANTANEOUS FORWARD RATE": "FF-1B-IFR"}),
        qfCreateBuildMethod("YIELD_CURVE_FUNDING", {"TARGET": FUNDING_INDEX, "REFERENCE INDEX": "SOFR-1B",
                                                    "INSTANTANEOUS FORWARD RATE": "SOFR-1B-FUNDING-IFR"}),
    ])
    return qfCreateModel(value_date, "YIELD_CURVE", data, methods)


def parameters():
    return qfCreateValuationParametersCollection(
        [qfCreateValuationParameters("FUNDING INDEX PARAMETER", {"FUNDING INDEX": FUNDING_INDEX})])


# ------------------------------------------------------------------ hand calculation, no library
def days(start, end):
    return (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days


def years(date, value_date=VALUE_DATE):
    # ACT/ACT (ISDA) from the value date; every date used here lies in 2026 or 2027, neither a leap year
    return days(value_date, date) / 365


def integral(nodes, date, value_date=VALUE_DATE):
    """integral_0^T f for the left-continuous step function: node i's rate applies on (t_{i-1}, t_i]
    and the last node's rate continues past its node."""
    T, total, lower = years(date, value_date), 0.0, 0.0
    for i, (node, rate) in enumerate(nodes):
        upper = math.inf if i == len(nodes) - 1 else years(node, value_date)
        total += rate * max(0.0, min(T, upper) - lower)
        lower = upper
    return total


def df_sofr(date):
    return math.exp(-integral(SOFR_IFR, date))


def df_ff(date):
    return math.exp(-integral(FF_IFR, date))


def df_funding(date):
    return df_sofr(date) * math.exp(-integral(SPREAD_IFR, date))


def act360(start, end):
    return days(start, end) / 360


def compounded_rate(df, start, end):
    """Compounded overnight rate of a coupon projected off curve df: the daily factors telescope."""
    return (df(start) / df(end) - 1.0) / act360(start, end)


def fixed_leg_pv(schedule, rate=FIXED_RATE, notional=NOTIONAL):
    return sum(notional * rate * act360(s, e) * df_funding(p) for s, e, p in schedule)


def overnight_leg_pv(schedule, df, spread=0.0, notional=NOTIONAL):
    return sum(notional * act360(s, e) * (compounded_rate(df, s, e) + spread) * df_funding(p) for s, e, p in schedule)


def business_day_intervals(start, end, calendar):
    """Consecutive business-day observation periods covering [start, end], as ISO strings."""
    dates = [d.ISO() for d in calendar.businessDayList(ql.DateParser.parseISO(start), ql.DateParser.parseISO(end))]
    return list(zip(dates[:-1], dates[1:]))


def grown_factor(calendar, start, end, value_date, rate):
    """Product of 1 + alpha_j * rate over the observation periods of [start, end] fixed before value_date."""
    factor = 1.0
    for s, e in business_day_intervals(start, end, calendar):
        if s < value_date:
            factor *= 1.0 + act360(s, e) * rate
    return factor


class flat_fixings:
    """Flat daily fixings for SOFR-1B and FF-1B on every calendar day of [first, last]; restores the singleton on exit."""

    def __init__(self, sofr_rate, ff_rate, first, last):
        self.rates, self.first, self.last = {"SOFR-1B": sofr_rate, "FF-1B": ff_rate}, first, last

    def __enter__(self):
        manager = IndexFixingsManager()
        self.saved = (dict(manager.daily_), dict(manager.term_))
        day = dt.date.fromisoformat(self.first)
        while day <= dt.date.fromisoformat(self.last):
            for index, rate in self.rates.items():
                manager.insert_fixing(index, Date(day.isoformat()), rate)
            day += dt.timedelta(days=1)
        return self

    def __exit__(self, *_):
        manager = IndexFixingsManager()
        manager.daily_.clear(); manager.daily_.update(self.saved[0])
        manager.term_.clear(); manager.term_.update(self.saved[1])
        return False


def engine_for(product, model=None, engine_cls=None):
    model = model or build()
    engine_cls = engine_cls or ValuationEngineProductRegistry().get((model.model_type, product.product_type, "ANALYTIC PARAMETER"))
    engine = engine_cls(model, parameters(), product, ValuationRequest.PV)
    engine.calculate_value()
    return engine


# ------------------------------------------------------------------------------------- RFR swap
def test_hand_discount_factors_match_the_model():
    model = build()
    for date in ("2026-07-02", "2026-10-06", "2027-01-06", "2027-04-06"):
        assert abs(model.discount_factor("SOFR-1B", Date(date)) - df_sofr(date)) < 1e-12
        assert abs(model.discount_factor("FF-1B", Date(date)) - df_ff(date)) < 1e-12
        assert abs(model.discount_factor(FUNDING_INDEX, Date(date)) - df_funding(date)) < 1e-12


def test_compounded_coupon_rate_telescopes_to_the_projection_curve_ratio():
    swap = make_swap(floating_leg_accrual_period="3M")
    leg_engine = ValuationEngineInterestRateStream(build(), parameters(), swap.floating_leg, ValuationRequest.PV)
    leg_engine.calculate_value()
    for i, (start, end, _) in enumerate(QUARTERLY):
        assert abs(leg_engine.rates_[i] - compounded_rate(df_sofr, start, end)) < 1e-12
        assert abs(leg_engine.accruals_[i] - act360(start, end)) < 1e-12


def test_fixed_leg_pv_is_notional_times_rate_times_accrual_discounted_on_the_funding_curve():
    engine = engine_for(make_swap())
    fixed = engine.fixed_leg_engine_
    assert abs(fixed.value - fixed_leg_pv(ANNUAL)) < TOL
    assert abs(fixed.value - NOTIONAL * FIXED_RATE * (365 / 360) * df_funding("2027-04-06")) < TOL


def test_receive_fixed_swap_is_fixed_leg_minus_floating_leg():
    engine = engine_for(make_swap())
    expected = fixed_leg_pv(ANNUAL) - overnight_leg_pv(ANNUAL, df_sofr)
    assert abs(engine.value - expected) < TOL
    assert engine.cash == 0.0
    assert engine.value < 0                                 # 4% fixed against a 4.27% compounded forward
    model = build()
    fixed_pv = qfCreateValueReport(model, engine.product_.fixed_leg, parameters(), "PV")[0][1]
    floating_pv = qfCreateValueReport(model, engine.product_.floating_leg, parameters(), "PV")[0][1]
    assert abs(engine.value - (fixed_pv - floating_pv)) < 1e-9


def test_pay_fixed_swap_is_the_mirror_image():
    receiver, payer = engine_for(make_swap()), engine_for(make_swap(pay_or_rec="pay"))
    assert abs(receiver.value + payer.value) < 1e-9
    assert payer.fixed_leg_sign_ == -1.0 and payer.floating_leg_sign_ == 1.0


def test_swap_with_quarterly_floating_leg_and_a_spread():
    swap = make_swap(floating_leg_accrual_period="3M", spread=0.0025)
    engine = engine_for(swap)
    expected = fixed_leg_pv(ANNUAL) - overnight_leg_pv(QUARTERLY, df_sofr, spread=0.0025)
    assert abs(engine.value - expected) < TOL
    flat = engine_for(make_swap(floating_leg_accrual_period="3M"))
    spread_annuity = sum(NOTIONAL * act360(s, e) * df_funding(p) for s, e, p in QUARTERLY)
    assert abs((flat.value - engine.value) - 0.0025 * spread_annuity) < TOL


def test_par_rate_from_the_hand_calculation_zeroes_the_swap():
    annuity = sum(NOTIONAL * act360(s, e) * df_funding(p) for s, e, p in ANNUAL)
    par = overnight_leg_pv(QUARTERLY, df_sofr) / annuity
    engine = engine_for(make_swap(fixed_rate=par, floating_leg_accrual_period="3M"))
    assert abs(engine.value) < TOL
    assert 0.042 < par < 0.044


def test_arithmetic_compounding_adds_the_daily_interest_instead_of_compounding_it():
    swap = make_swap(compounding_method="arithmetic")
    engine = engine_for(swap)
    rate = engine.floating_leg_engine_.rates_[0]
    intervals = business_day_intervals(EFFECTIVE_DATE, END_DATE, ql.UnitedStates(ql.UnitedStates.SOFR))
    simple_sum = sum(df_sofr(s) / df_sofr(e) - 1.0 for s, e in intervals)
    assert abs(rate - simple_sum / act360(EFFECTIVE_DATE, END_DATE)) < 1e-12
    assert rate < compounded_rate(df_sofr, EFFECTIVE_DATE, END_DATE)      # no interest on interest


def test_swap_paying_on_the_value_date_is_cash_from_historical_fixings():
    with flat_fixings(0.041, 0.0, "2026-03-27", "2027-04-05"):
        model = build("2027-04-06", sofr=[("2027-07-06", 0.03), ("2028-01-03", 0.04)],
                      fed_funds=[("2027-07-06", 0.028), ("2028-01-03", 0.037)],
                      spread=[("2027-07-06", 0.0), ("2028-01-03", 0.001)])
        engine = engine_for(make_swap(), model)
        growth = grown_factor(ql.UnitedStates(ql.UnitedStates.SOFR), EFFECTIVE_DATE, END_DATE, "2027-04-06", 0.041)
        expected = NOTIONAL * (FIXED_RATE * act360(EFFECTIVE_DATE, END_DATE) - (growth - 1.0))
        assert abs(engine.value - expected) < TOL
        assert abs(engine.cash - expected) < TOL                 # paid today: cash, not discounted
    assert not IndexFixingsManager().exist_fixing("SOFR-1B", Date("2026-06-01"))   # singleton restored


def test_mid_life_swaps_separate_todays_coupon_as_cash_from_the_discounted_remainder():
    """Value date 2026-07-07, the first quarterly payment date: the first coupon of each leg is cash, built from
    the fixings of the index's own calendar; the second coupon mixes fixings before the value date with the
    projection curve after it; the last two are projected and discounted. Cash is neither zero nor the value."""
    value_date = "2026-07-07"
    sofr_nodes, ff_nodes = [("2027-01-04", 0.04), ("2028-01-03", 0.05)], [("2027-01-04", 0.037), ("2028-01-03", 0.037)]
    spread_nodes = [("2027-01-04", 0.001), ("2028-01-03", 0.001)]
    sofr_fixing, ff_fixing = 0.041, 0.038
    sofr_calendar, ff_calendar = ql.UnitedStates(ql.UnitedStates.SOFR), ql.UnitedStates(ql.UnitedStates.FederalReserve)
    df_s = lambda d: math.exp(-integral(sofr_nodes, d, value_date))
    df_f = lambda d: math.exp(-integral(ff_nodes, d, value_date))
    df_fund = lambda d: df_s(d) * math.exp(-integral(spread_nodes, d, value_date))

    def coupon_rate(df, calendar, fixing, start, end):
        grown = grown_factor(calendar, start, end, value_date, fixing)
        return (grown * df(max(start, value_date)) / df(end) - 1.0) / act360(start, end)

    def leg(df, calendar, fixing, spread):
        """(cash today, discounted value of the later coupons) of a quarterly overnight leg."""
        first, later = QUARTERLY[0], QUARTERLY[1:]
        cash = NOTIONAL * act360(first[0], first[1]) * (coupon_rate(df, calendar, fixing, first[0], first[1]) + spread)
        value = sum(NOTIONAL * act360(s, e) * (coupon_rate(df, calendar, fixing, s, e) + spread) * df_fund(p) for s, e, p in later)
        return cash, value

    with flat_fixings(sofr_fixing, ff_fixing, "2026-03-20", "2026-07-06"):
        model = build(value_date, sofr=sofr_nodes, fed_funds=ff_nodes, spread=spread_nodes)
        sofr_cash, sofr_later = leg(df_s, sofr_calendar, sofr_fixing, BASIS_SPREAD)
        ff_cash, ff_later = leg(df_f, ff_calendar, ff_fixing, 0.0)
        basis = engine_for(make_basis_swap(), model)
        assert abs(basis.cash - (sofr_cash - ff_cash)) < TOL
        assert abs(basis.value - ((sofr_cash - ff_cash) + (sofr_later - ff_later))) < TOL
        assert basis.cash != 0.0 and abs(basis.value - basis.cash) > 1.0
        float_cash, float_later = leg(df_s, sofr_calendar, sofr_fixing, 0.0)
        fixed_value = NOTIONAL * FIXED_RATE * act360(EFFECTIVE_DATE, END_DATE) * df_fund("2027-04-06")
        swap = engine_for(make_swap(floating_leg_accrual_period="3M"), model)
        assert abs(swap.cash - (-float_cash)) < TOL                 # receive fixed: today's floating coupon is paid out
        assert abs(swap.value - (-float_cash + fixed_value - float_later)) < TOL
        assert swap.cash != 0.0 and abs(swap.value - swap.cash) > 1.0


def test_swap_whose_payments_are_all_in_the_past_is_worthless():
    model = build("2027-06-01", sofr=[("2027-09-01", 0.03), ("2028-01-03", 0.04)],
                  fed_funds=[("2027-09-01", 0.028), ("2028-01-03", 0.037)],
                  spread=[("2027-09-01", 0.0), ("2028-01-03", 0.001)])
    engine = engine_for(make_swap(floating_leg_accrual_period="3M"), model)
    assert engine.value == 0.0 and engine.cash == 0.0
    basis = engine_for(make_basis_swap(), model)
    assert basis.value == 0.0 and basis.cash == 0.0


def test_swap_cashflow_report_carries_leg_names_and_signs():
    swap = make_swap(floating_leg_accrual_period="3M")
    engine = engine_for(swap)
    rows = engine.create_cash_flows_report().content
    assert [row["Leg"] for row in rows] == ["Fixed"] + ["Floating"] * 4
    assert rows[0]["Notional"] == NOTIONAL and all(row["Notional"] == -NOTIONAL for row in rows[1:])
    assert abs(sum(row["PV"] for row in rows) - engine.value) < 1e-9
    frame = qfCreateCashflowsReport(build(), swap, parameters()).display()
    assert list(frame["Payment Date"]) == ["2027-04-06"] + [p for _, _, p in QUARTERLY]


# ----------------------------------------------------------------------------------- basis swap
def test_basis_swap_is_leg_1_with_spread_minus_leg_2():
    engine = engine_for(make_basis_swap())
    leg_1 = overnight_leg_pv(QUARTERLY, df_sofr, spread=BASIS_SPREAD)
    leg_2 = overnight_leg_pv(QUARTERLY, df_ff)
    assert abs(engine.value - (leg_1 - leg_2)) < TOL
    assert engine.cash == 0.0
    model = build()
    leg_1_report = qfCreateValueReport(model, engine.product_.floating_leg_1, parameters(), "PV")[0][1]
    leg_2_report = qfCreateValueReport(model, engine.product_.floating_leg_2, parameters(), "PV")[0][1]
    assert abs(engine.value - (leg_1_report - leg_2_report)) < 1e-9


def test_basis_swap_components_are_index_spread_and_leg_2():
    engine = engine_for(make_basis_swap())
    index_only, spread_only, leg_2 = (eng for _, _, eng in engine._legs())
    assert abs(index_only.value - overnight_leg_pv(QUARTERLY, df_sofr)) < TOL
    spread_annuity = sum(NOTIONAL * act360(s, e) * df_funding(p) for s, e, p in QUARTERLY)
    assert abs(spread_only.value - BASIS_SPREAD * spread_annuity) < TOL
    assert abs(leg_2.value - overnight_leg_pv(QUARTERLY, df_ff)) < TOL
    assert abs(engine.value - (index_only.value + spread_only.value - leg_2.value)) < 1e-9


def test_basis_swap_spread_enters_linearly_and_the_pay_side_flips_the_sign():
    with_spread, flat = engine_for(make_basis_swap()), engine_for(make_basis_swap(spread_over_leg_1=0.0))
    spread_annuity = sum(NOTIONAL * act360(s, e) * df_funding(p) for s, e, p in QUARTERLY)
    assert abs((with_spread.value - flat.value) - BASIS_SPREAD * spread_annuity) < TOL
    payer = engine_for(make_basis_swap(pay_or_rec_leg_1="pay"))
    assert abs(payer.value + with_spread.value) < 1e-9
    assert payer.floating_leg_1_sign_ == -1.0 and payer.floating_leg_2_sign_ == 1.0


def test_fair_basis_spread_from_the_hand_calculation_zeroes_the_swap():
    spread_annuity = sum(NOTIONAL * act360(s, e) * df_funding(p) for s, e, p in QUARTERLY)
    fair = (overnight_leg_pv(QUARTERLY, df_ff) - overnight_leg_pv(QUARTERLY, df_sofr)) / spread_annuity
    engine = engine_for(make_basis_swap(spread_over_leg_1=fair))
    assert abs(engine.value) < TOL
    assert fair < 0                                           # Fed Funds projects below SOFR here


def test_basis_swap_with_different_leg_periods():
    engine = engine_for(make_basis_swap(accrual_period_2="6M"))
    semi_annual = [("2026-04-02", "2026-10-02", "2026-10-06"), ("2026-10-02", "2027-04-02", "2027-04-06")]
    expected = overnight_leg_pv(QUARTERLY, df_sofr, spread=BASIS_SPREAD) - overnight_leg_pv(semi_annual, df_ff)
    assert abs(engine.value - expected) < TOL


def test_basis_swap_cashflow_report_has_twelve_signed_rows():
    engine = engine_for(make_basis_swap())
    rows = engine.create_cash_flows_report().content
    assert [row["Leg"] for row in rows] == ["Leg 1 index"] * 4 + ["Leg 1 spread"] * 4 + ["Leg 2 index"] * 4
    assert all(row["Notional"] == NOTIONAL for row in rows[:8]) and all(row["Notional"] == -NOTIONAL for row in rows[8:])
    assert all(abs(row["Rate"] - BASIS_SPREAD) < 1e-15 for row in rows[4:8])
    assert abs(sum(row["PV"] for row in rows) - engine.value) < 1e-9


# ----------------------------------------------------------------------- dispatch and the FRA example
def test_registry_dispatches_the_swap_engines_and_the_public_report_agrees():
    model = build()
    swap, basis = make_swap(), make_basis_swap()
    assert isinstance(ValuationEngineProductRegistry.new_valuation_engine(model, swap, parameters(), ValuationRequest.PV),
                      ValuationEngineProductRfrSwap)
    assert isinstance(ValuationEngineProductRegistry.new_valuation_engine(model, basis, parameters(), ValuationRequest.PV),
                      ValuationEngineProductOvernightIndexBasisSwap)
    assert qfCreateValueReport(model, swap, parameters(), "PV") == [["USD", engine_for(swap, model).value]]
    assert qfCreateValueReport(model, basis, parameters(), "PV") == [["USD", engine_for(basis, model).value]]


def test_factory_products_value_the_same_as_direct_ones():
    model = build()
    for convention, direct, quote in ((SWAP_CONVENTION, make_swap(), FIXED_RATE), (BASIS_CONVENTION, make_basis_swap(), BASIS_SPREAD)):
        created = qfCreateProductFromDataConvention(VALUE_DATE, convention, f"{EFFECTIVE_DATE}x{END_DATE}", quote,
                                                    notional=NOTIONAL, pay_or_rec="receive")
        assert qfCreateValueReport(model, created, parameters(), "PV") == qfCreateValueReport(model, direct, parameters(), "PV")


def test_supplied_fra_example_still_matches_its_formula():
    fra = qfCreateProductFRA(EFFECTIVE_DATE, "2026-07-02", "SOFR-1B", FIXED_RATE, "receive", NOTIONAL, accrual_basis="ACT/360")
    engine = engine_for(fra, engine_cls=ValuationEngineProductFra)
    forward = (df_sofr(EFFECTIVE_DATE) / df_sofr("2026-07-02") - 1.0) / act360(EFFECTIVE_DATE, "2026-07-02")
    expected = NOTIONAL * act360(EFFECTIVE_DATE, "2026-07-02") * (FIXED_RATE - forward) * df_funding("2026-07-02")
    assert abs(engine.value - expected) < TOL


if __name__ == "__main__":
    tests = [obj for name, obj in sorted(globals().items()) if name.startswith("test_") and callable(obj)]
    for test in tests:
        test()
        print(f"PASS  {test.__name__}")
    print(f"\n{len(tests)} tests passed")

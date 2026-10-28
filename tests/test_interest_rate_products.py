"""Checks for the two swap products and the convention-driven factory added for HW6
(fixedincomelib/product/linear_products.py and fixedincomelib/product/product_factory.py).

    python tests/test_interest_rate_products.py    # plain runner
    python -m pytest tests -q                      # with pytest

The trades are the ones in hw6_interest_rate_products.ipynb. Expected dates were worked out by hand
with the SOFR fixing calendar and the US government bond calendar: a quarterly schedule from
2026-04-02 to 2027-04-02 ends on 2026-07-02, 2026-10-02, 2027-01-04 (2027-01-02 is a Saturday) and
2027-04-02, and each coupon pays two business days later.
"""
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from fixedincomelib import (  # noqa: E402
    qfCreateProductFromDataConvention, qfCreateProductOvernightIndexBasisSwap, qfCreateProductRFRSwap,
    qfDisplayProduct,
)
from fixedincomelib.market.data_conventions import CompoundingMethod  # noqa: E402
from fixedincomelib.market.registries import DataConventionRegistry  # noqa: E402
from fixedincomelib.product import (  # noqa: E402
    PayOrReceive, ProductBuilderRegistry, ProductFactory, ProductFixedAccruedCashflow,
    ProductOvernightIndexBasisSwap, ProductOvernightIndexCashflow, ProductRFRSwap,
)

VALUE_DATE = "2026-01-02"
EFFECTIVE_DATE = "2026-04-02"
END_DATE = "2027-04-02"
NOTIONAL = 1_000_000
FIXED_RATE = 0.04
BASIS_SPREAD = 0.001
SWAP_CONVENTION = "USD-SOFR-OIS"
BASIS_CONVENTION = "USD-FF-3M-OVER-USD-SOFR-OIS-3M"
# (accrual start, accrual end, payment date) worked out by hand, see the module docstring
QUARTERLY = [("2026-04-02", "2026-07-02", "2026-07-07"), ("2026-07-02", "2026-10-02", "2026-10-06"),
             ("2026-10-02", "2027-01-04", "2027-01-06"), ("2027-01-04", "2027-04-02", "2027-04-06")]
ANNUAL = [("2026-04-02", "2027-04-02", "2027-04-06")]
SEMI_ANNUAL = [("2026-04-02", "2026-10-02", "2026-10-06"), ("2026-10-02", "2027-04-02", "2027-04-06")]


def make_swap(**overrides):
    args = dict(effective_date=EFFECTIVE_DATE, term_or_termination_date=END_DATE, payment_off_set="2D",
                on_index="SOFR-1B", fixed_rate=FIXED_RATE, pay_or_rec="receive", notional=NOTIONAL,
                accrual_period="1Y", accrual_basis="ACT/360", floating_leg_accrual_period="1Y")
    args.update(overrides)
    return qfCreateProductRFRSwap(**args)


def make_basis_swap(**overrides):
    args = dict(effective_date=EFFECTIVE_DATE, term_or_termination_date=END_DATE, payment_off_set="2D",
                on_index_leg_1="SOFR-1B", on_index_leg_2="FF-1B", spread_over_leg_1=BASIS_SPREAD,
                pay_or_rec_leg_1="receive", notional=NOTIONAL, accrual_period_1="3M", accrual_period_2="3M",
                accrual_basis="ACT/360")
    args.update(overrides)
    return qfCreateProductOvernightIndexBasisSwap(**args)


def dates_of(leg):
    return [(leg.cashflow(i).effective_date.ISO(), leg.cashflow(i).termination_date.ISO(),
             leg.cashflow(i).payment_date.ISO()) for i in range(leg.num_cashflows())]


def coupons(leg):
    return [leg.cashflow(i) for i in range(leg.num_cashflows())]


# ---------------------------------------------------------------------------------- RFR swap product
def test_rfr_swap_fixed_leg_is_a_fixed_accrued_coupon_per_period():
    swap = make_swap()
    leg = swap.fixed_leg
    assert leg.num_cashflows() == 1 and dates_of(leg) == ANNUAL
    coupon = leg.cashflow(0)
    assert isinstance(coupon, ProductFixedAccruedCashflow)
    assert leg.fixed_rate == FIXED_RATE and leg.float_index is None
    assert coupon.notional == NOTIONAL and coupon.currency.code() == "USD"
    assert abs(coupon.accrued - 365 / 360) < 1e-12          # ACT/360 over the 365-day period


def test_rfr_swap_floating_leg_compounds_the_overnight_index_on_the_same_dates():
    swap = make_swap()
    leg = swap.floating_leg
    assert leg.num_cashflows() == 1 and dates_of(leg) == dates_of(swap.fixed_leg)
    coupon = leg.cashflow(0)
    assert isinstance(coupon, ProductOvernightIndexCashflow)
    assert leg.float_index == "SOFR-1B" and leg.is_on_index_ is True
    assert coupon.on_index.name() == swap.on_index.name()
    assert coupon.compounding_method == CompoundingMethod.COMPOUND
    assert coupon.spread == 0.0 and coupon.notional == NOTIONAL


def test_rfr_swap_legs_follow_the_index_calendar_and_the_swap_payment_terms():
    swap = make_swap()
    for leg in (swap.fixed_leg, swap.floating_leg):
        spec = leg.serialize()
        assert spec["HOLIDAY_CONVENTION"] == "SOFR fixing calendar"
        assert spec["BUSINESS_DAY_CONVENTION"] == "F"
        assert spec["PAYMENT_OFFSET"] == "2D"
        assert spec["PAYMENT_BUSINESS_DAY_CONVENTION"] == "F" and spec["PAYMENT_HOLIDAY_CONVENTION"] == "USGS"
        assert spec["ACCRUAL_BASIS"] == "ACT/360" and spec["NOTIONAL"] == NOTIONAL


def test_rfr_swap_legs_can_have_different_accrual_periods():
    swap = make_swap(accrual_period="1Y", floating_leg_accrual_period="3M")
    assert dates_of(swap.fixed_leg) == ANNUAL
    assert dates_of(swap.floating_leg) == QUARTERLY
    assert swap.last_date.ISO() == "2027-04-06"
    assert str(swap.accrual_period) == "1Y" and str(swap.floating_leg_accrual_period) == "3M"


def test_rfr_swap_spread_and_compounding_method_reach_every_floating_coupon():
    swap = make_swap(floating_leg_accrual_period="3M", spread=0.0025, compounding_method="arithmetic")
    for coupon in coupons(swap.floating_leg):
        assert coupon.spread == 0.0025
        assert coupon.compounding_method == CompoundingMethod.ARITHMETIC
    assert swap.fixed_leg.fixed_rate == FIXED_RATE          # the fixed leg is untouched by the spread
    assert swap.spread == 0.0025 and swap.compounding_method == CompoundingMethod.ARITHMETIC


def test_rfr_swap_tenor_end_is_rolled_with_the_index_calendar():
    one_year = make_swap(term_or_termination_date="1Y")
    assert one_year.termination_date.ISO() == "2027-04-02"
    assert dates_of(one_year.fixed_leg) == ANNUAL and dates_of(one_year.floating_leg) == ANNUAL
    assert one_year.serialize()["TERM_OR_TERMINATION_DATE"] == "1Y"
    nine_months = make_swap(term_or_termination_date="9M", accrual_period="9M", floating_leg_accrual_period="9M")
    assert nine_months.termination_date.ISO() == "2027-01-04"     # 2027-01-02 is a Saturday: Following
    assert nine_months.last_date.ISO() == "2027-01-06"
    for leg in (nine_months.fixed_leg, nine_months.floating_leg):
        assert leg.cashflow(0).effective_date.ISO() == EFFECTIVE_DATE
        assert leg.cashflow(leg.num_cashflows() - 1).termination_date.ISO() == "2027-01-04"
        assert leg.cashflow(leg.num_cashflows() - 1).payment_date.ISO() == "2027-01-06"


def test_rfr_swap_pay_direction_and_notional_sign_are_kept():
    payer = make_swap(pay_or_rec="pay")
    assert payer.pay_or_rec == PayOrReceive.PAY
    assert payer.serialize()["PAY_OR_REC"] == "PAY"
    assert payer.fixed_leg.cashflow(0).notional == NOTIONAL      # legs are unsigned; the engine applies the sign


def test_rfr_swap_survives_a_serialization_round_trip():
    swap = make_swap(floating_leg_accrual_period="3M", spread=0.001)
    rebuilt = ProductRFRSwap.deserialize(swap.serialize())
    assert rebuilt.serialize() == swap.serialize()
    assert dates_of(rebuilt.fixed_leg) == dates_of(swap.fixed_leg)
    assert dates_of(rebuilt.floating_leg) == dates_of(swap.floating_leg)
    assert [c.spread for c in coupons(rebuilt.floating_leg)] == [0.001] * 4
    via_registry = ProductBuilderRegistry().get(ProductRFRSwap._product_type + "_DES")(swap.serialize())
    assert via_registry.serialize() == swap.serialize()


def test_rfr_swap_display_lists_the_contract_terms():
    frame = qfDisplayProduct(make_swap())
    shown = dict(zip(frame["Name"], frame["Value"]))
    assert shown["Product Type"] == "PRODUCT_RFR_SWAP"
    assert shown["Effective Date"] == EFFECTIVE_DATE and shown["Termination Date"] == END_DATE
    assert shown["Last Payment Date"] == "2027-04-06"
    assert shown["ON Index"] == "SOFR-1B" and shown["Pay Or Receive Fixed"] == "RECEIVE"
    assert shown["Fixed Accrual Period"] == "1Y" and shown["Floating Accrual Period"] == "1Y"


# ---------------------------------------------------------------------------- basis swap product
def test_basis_swap_leg_1_carries_the_spread_and_leg_2_does_not():
    swap = make_basis_swap()
    leg_1, leg_2 = swap.floating_leg_1, swap.floating_leg_2
    assert dates_of(leg_1) == QUARTERLY and dates_of(leg_2) == QUARTERLY
    for coupon in coupons(leg_1):
        assert isinstance(coupon, ProductOvernightIndexCashflow)
        assert coupon.on_index.name() == swap.on_index_1.name() and coupon.spread == BASIS_SPREAD
        assert coupon.compounding_method == CompoundingMethod.COMPOUND and coupon.notional == NOTIONAL
    for coupon in coupons(leg_2):
        assert isinstance(coupon, ProductOvernightIndexCashflow)
        assert coupon.on_index.name() == swap.on_index_2.name() and coupon.spread == 0.0
        assert coupon.compounding_method == CompoundingMethod.COMPOUND and coupon.notional == NOTIONAL
    assert leg_1.float_index == "SOFR-1B" and leg_2.float_index == "FF-1B"


def test_basis_swap_each_leg_follows_its_own_index_calendar():
    swap = make_basis_swap()
    assert swap.floating_leg_1.serialize()["HOLIDAY_CONVENTION"] == "SOFR fixing calendar"
    assert swap.floating_leg_2.serialize()["HOLIDAY_CONVENTION"] == "Federal Reserve Bankwire System"
    for leg in (swap.floating_leg_1, swap.floating_leg_2):
        spec = leg.serialize()
        assert spec["PAYMENT_OFFSET"] == "2D" and spec["PAYMENT_HOLIDAY_CONVENTION"] == "USGS"
        assert spec["BUSINESS_DAY_CONVENTION"] == "F" and spec["PAYMENT_BUSINESS_DAY_CONVENTION"] == "F"


def test_basis_swap_leg_1_splits_into_the_supplied_index_and_spread_streams():
    swap = make_basis_swap()
    index_only, spread_only = swap.floating_leg_1_wo_basis, swap.floating_leg_1_basis
    assert dates_of(index_only) == dates_of(swap.floating_leg_1) == dates_of(spread_only)
    assert all(c.spread == 0.0 for c in coupons(index_only))
    assert spread_only.fixed_rate == BASIS_SPREAD and spread_only.float_index is None
    for full, part in zip(coupons(swap.floating_leg_1), coupons(spread_only)):
        day_count = full.on_index.dayCounter().yearFraction(full.effective_date, full.termination_date)
        assert abs(part.accrued - day_count) < 1e-12        # same accrual, so leg 1 = index + spread exactly


def test_basis_swap_legs_can_have_different_accrual_periods():
    swap = make_basis_swap(accrual_period_1="3M", accrual_period_2="6M")
    assert dates_of(swap.floating_leg_1) == QUARTERLY
    assert dates_of(swap.floating_leg_2) == SEMI_ANNUAL
    assert swap.last_date.ISO() == "2027-04-06"
    assert str(swap.accrual_period_leg_1) == "3M" and str(swap.accrual_period_leg_2) == "6M"


def test_basis_swap_tenor_end_is_rolled_with_the_leg_1_index_calendar():
    one_year = make_basis_swap(term_or_termination_date="1Y")
    assert one_year.termination_date.ISO() == "2027-04-02"
    assert dates_of(one_year.floating_leg_1) == QUARTERLY and dates_of(one_year.floating_leg_2) == QUARTERLY
    swap = make_basis_swap(term_or_termination_date="9M", accrual_period_1="9M", accrual_period_2="9M")
    assert swap.termination_date.ISO() == "2027-01-04" and swap.last_date.ISO() == "2027-01-06"
    for leg in (swap.floating_leg_1, swap.floating_leg_2):
        assert leg.cashflow(leg.num_cashflows() - 1).termination_date.ISO() == "2027-01-04"
        assert leg.cashflow(leg.num_cashflows() - 1).payment_date.ISO() == "2027-01-06"


def test_basis_swap_survives_a_serialization_round_trip():
    swap = make_basis_swap(accrual_period_2="6M", pay_or_rec_leg_1="pay")
    rebuilt = ProductOvernightIndexBasisSwap.deserialize(swap.serialize())
    assert rebuilt.serialize() == swap.serialize()
    assert rebuilt.pay_or_rec == PayOrReceive.PAY
    assert dates_of(rebuilt.floating_leg_1) == QUARTERLY and dates_of(rebuilt.floating_leg_2) == SEMI_ANNUAL
    assert [c.spread for c in coupons(rebuilt.floating_leg_1)] == [BASIS_SPREAD] * 4


def test_basis_swap_display_lists_both_indices_and_periods():
    frame = qfDisplayProduct(make_basis_swap())
    shown = dict(zip(frame["Name"], frame["Value"]))
    assert shown["ON Index Leg 1"] == "SOFR-1B" and shown["ON Index Leg 2"] == "FF-1B"
    assert shown["Spread Over Leg 1"] == BASIS_SPREAD and shown["Pay Or Receive Leg 1"] == "RECEIVE"
    assert shown["Last Payment Date"] == "2027-04-06"


# ----------------------------------------------------------------------------------------- factory
def test_factory_swap_from_explicit_dates_matches_direct_construction():
    created = qfCreateProductFromDataConvention(VALUE_DATE, SWAP_CONVENTION, f"{EFFECTIVE_DATE}x{END_DATE}",
                                                FIXED_RATE, notional=NOTIONAL, pay_or_rec="receive")
    assert isinstance(created, ProductRFRSwap)
    assert created.serialize() == make_swap().serialize()
    assert dates_of(created.fixed_leg) == ANNUAL and dates_of(created.floating_leg) == ANNUAL


def test_factory_basis_swap_from_explicit_dates_matches_direct_construction():
    created = qfCreateProductFromDataConvention(VALUE_DATE, BASIS_CONVENTION, f"{EFFECTIVE_DATE}x{END_DATE}",
                                                BASIS_SPREAD, notional=NOTIONAL, pay_or_rec="receive")
    assert isinstance(created, ProductOvernightIndexBasisSwap)
    assert created.serialize() == make_basis_swap().serialize()
    assert dates_of(created.floating_leg_1) == QUARTERLY and dates_of(created.floating_leg_2) == QUARTERLY


def test_factory_reads_the_convention_for_everything_but_dates_and_quote():
    convention = DataConventionRegistry().get(SWAP_CONVENTION)
    swap = qfCreateProductFromDataConvention(VALUE_DATE, SWAP_CONVENTION, "3Mx1Y", 0.0375)
    content = swap.serialize()
    assert content["ON_INDEX"] == convention.index_str == "SOFR-1B"
    assert content["ACCRUAL_PERIOD"] == content["FLOATING_LEG_ACCRUAL_PERIOD"] == "1Y"
    assert content["PAYMENT_OFFSET"] == "2D" and content["ACCRUAL_BASIS"] == "ACT/360"
    assert content["PAY_BUSINESS_DAY_CONVENTION"] == "F" and content["PAY_HOLIDAY_CONVENTION"] == "USGS"
    assert content["COMPOUNDING_METHOD"] == "COMPOUND" and content["SPREAD"] == 0.0
    assert content["FIXED_RATE"] == 0.0375                      # the quote is the fixed rate
    assert content["NOTIONAL"] == 1e4 and content["PAY_OR_REC"] == "RECEIVE"   # the FRA builder's defaults
    basis = qfCreateProductFromDataConvention(VALUE_DATE, BASIS_CONVENTION, "3Mx1Y", 0.0012, pay_or_rec="pay")
    content = basis.serialize()
    assert content["ON_INDEX_LEG_1"] == "SOFR-1B" and content["ON_INDEX_LEG_2"] == "FF-1B"
    assert content["SPREAD_OVER_LEG_1"] == 0.0012                 # the quote is the spread on leg 1
    assert content["ACCRUAL_PERIOD_1"] == content["ACCRUAL_PERIOD_2"] == "3M"
    assert content["PAY_OR_REC_LEG_1"] == "PAY" and content["NOTIONAL"] == 1e4


def test_factory_axis1_rules_for_swaps():
    forward_start = qfCreateProductFromDataConvention(VALUE_DATE, SWAP_CONVENTION, "3Mx1Y", FIXED_RATE)
    assert forward_start.effective_date.ISO() == "2026-04-02"      # value date + 3M
    assert forward_start.termination_date.ISO() == "2027-04-02"    # then 1Y with the index calendar
    assert forward_start.serialize()["TERM_OR_TERMINATION_DATE"] == "1Y"
    spot_start = qfCreateProductFromDataConvention(VALUE_DATE, SWAP_CONVENTION, "1Y", FIXED_RATE)
    assert spot_start.effective_date.ISO() == VALUE_DATE
    assert spot_start.termination_date.ISO() == "2027-01-04"        # 2027-01-02 is a Saturday
    mixed = qfCreateProductFromDataConvention(VALUE_DATE, BASIS_CONVENTION, f"3Mx{END_DATE}", BASIS_SPREAD)
    assert mixed.effective_date.ISO() == "2026-04-02" and mixed.termination_date.ISO() == END_DATE
    assert mixed.serialize()["TERM_OR_TERMINATION_DATE"] == END_DATE
    dated_start = qfCreateProductFromDataConvention(VALUE_DATE, BASIS_CONVENTION, f"{EFFECTIVE_DATE}x1Y", BASIS_SPREAD)
    assert dated_start.effective_date.ISO() == EFFECTIVE_DATE and dated_start.termination_date.ISO() == END_DATE
    upper_case = qfCreateProductFromDataConvention(VALUE_DATE, SWAP_CONVENTION, "3MX1Y", FIXED_RATE)
    assert upper_case.serialize() == forward_start.serialize()


def test_factory_builders_are_registered_for_both_convention_types():
    registry = ProductBuilderRegistry()
    assert registry.get("RFR SWAP") == ProductFactory.create_rfr_swap          # bound classmethods compare by function
    assert registry.get("OVERNIGHT INDEX BASIS SWAP") == ProductFactory.create_overnight_index_basis_swap
    assert registry.get("FRA") == ProductFactory.create_fra
    assert DataConventionRegistry().get(SWAP_CONVENTION).type() == "RFR SWAP"
    assert DataConventionRegistry().get(BASIS_CONVENTION).type() == "OVERNIGHT INDEX BASIS SWAP"


if __name__ == "__main__":
    tests = [obj for name, obj in sorted(globals().items()) if name.startswith("test_") and callable(obj)]
    for test in tests:
        test()
        print(f"PASS  {test.__name__}")
    print(f"\n{len(tests)} tests passed")

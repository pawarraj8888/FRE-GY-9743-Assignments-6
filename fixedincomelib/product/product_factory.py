"""Convention-driven factory adapted from the instructor template.

Swap axis1 is tenor or start-offset x tenor. FRA uses start-offset x end-offset,
with both offsets measured from value_date, or two explicit ISO dates.
"""

from typing import Any
from fixedincomelib.date import Date, TermOrDate, add_period
from fixedincomelib.market.data_conventions import (
    CompoundingMethod, DataConvention, DataConventionFRA,
    DataConventionRFRSwap, DataConventionOvernightIndexBasisSwap,
)
from fixedincomelib.product.product_interfaces import ProductBuilderRegistry
from fixedincomelib.product.linear_products import ProductFRA, ProductRFRSwap, ProductOvernightIndexBasisSwap
from fixedincomelib.product.utilities import PayOrReceive


class ProductFactory:
    @classmethod
    def create_product_from_data_convention(
        cls,
        value_date: Date,
        axis1: str,
        data_convention: DataConvention,
        values: float,
        **kwargs: Any,
    ):

        convention_obj: DataConvention = data_convention
        prod_type = convention_obj.type()
        func = ProductBuilderRegistry().get(prod_type)
        return func(value_date, axis1, convention_obj, values, **kwargs)

    @classmethod
    def create_rfr_swap(
        cls,
        value_date: Date,
        axis1: str,
        data_convention: DataConventionRFRSwap,
        values: float,
        **kwargs: Any,
    ) -> ProductRFRSwap:

        # The convention fixes the index, accrual basis and period, payment offset and payment
        # conventions; axis1 fixes the dates and the quote is the fixed rate. The swap has one
        # accrual period for both legs, so the floating leg reuses the convention's period.
        effective_date, term_or_termination_date = cls._swap_dates(value_date, axis1, data_convention)
        return ProductRFRSwap(
            effective_date, term_or_termination_date, data_convention.payment_offset,
            data_convention.index_str, values,
            PayOrReceive.from_string(kwargs.get("pay_or_rec", "receive")),
            kwargs.get("notional", 1e4), data_convention.acc_period, data_convention.acc_basis,
            data_convention.acc_period, data_convention.business_day_convention,
            data_convention.holiday_convention, 0.0, data_convention.compounding_method,
        )

    @classmethod
    def create_overnight_index_basis_swap(
        cls,
        value_date: Date,
        axis1: str,
        data_convention: DataConventionOvernightIndexBasisSwap,
        values: float,
        **kwargs: Any,
    ) -> ProductOvernightIndexBasisSwap:

        # Leg 1 is the convention's basis index plus the quoted spread, leg 2 its reference
        # index flat; each leg keeps its own accrual period and both share the payment terms.
        effective_date, term_or_termination_date = cls._swap_dates(value_date, axis1, data_convention)
        return ProductOvernightIndexBasisSwap(
            effective_date, term_or_termination_date, data_convention.payment_offset,
            data_convention.index_1_str, data_convention.index_2_str, values,
            PayOrReceive.from_string(kwargs.get("pay_or_rec", "receive")),
            kwargs.get("notional", 1e4), data_convention.acc_period_1, data_convention.acc_basis,
            data_convention.acc_period_2, data_convention.business_day_convention,
            data_convention.holiday_convention, data_convention.compounding_method,
        )

    @classmethod
    def create_fra(cls, value_date, axis1, data_convention, values, **kwargs):
        start, end = cls._tokenize_axis1(axis1)
        bdc = data_convention.business_day_convention
        holidays = data_convention.holiday_convention
        if start.is_term():
            effective_date = add_period(value_date, start.get_term(), bdc, holidays)
            termination_date = add_period(value_date, end.get_term(), bdc, holidays)
        else:
            effective_date = start.get_date()
            termination_date = end.get_date()
        return ProductFRA(
            effective_date, TermOrDate(termination_date), data_convention.index_str,
            values, PayOrReceive.from_string(kwargs.get("pay_or_rec", "receive")),
            kwargs.get("notional", 1e4), data_convention.acc_basis, bdc, holidays,
        )

    @classmethod
    def _swap_dates(cls, value_date, axis1, data_convention):
        """Swap date rule: '1Y' starts spot and runs for the tenor; '3Mx1Y' starts in 3M and runs
        for 1Y; either token may instead be an explicit ISO date. The product adjusts the start
        and resolves a tenor end with the index calendar, so only the start offset is applied here."""
        start, end = cls._tokenize_axis1(axis1)
        if end is None:
            return value_date, start
        if start.is_term():
            effective_date = add_period(
                value_date, start.get_term(), data_convention.business_day_convention,
                data_convention.holiday_convention,
            )
        else:
            effective_date = start.get_date()
        return effective_date, end

    @staticmethod
    def _tokenize_axis1(axis1):
        tokens = axis1.strip().replace("X", "x").split("x")
        first = TermOrDate(tokens[0].strip())
        second = TermOrDate(tokens[1].strip()) if len(tokens) == 2 else None
        return first, second


ProductBuilderRegistry().register(DataConventionFRA.type(), ProductFactory.create_fra)
ProductBuilderRegistry().register(DataConventionRFRSwap.type(), ProductFactory.create_rfr_swap)
ProductBuilderRegistry().register(DataConventionOvernightIndexBasisSwap.type(),
                                  ProductFactory.create_overnight_index_basis_swap)

from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.tracking.models import WorkSession
from .models import BillingUnit, Invoice, PayoutBatch

from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from apps.tracking.models import WorkSession
from .models import BillingUnit

def create_billing_unit_for_session(session: WorkSession):
    contract = session.contract
    offer = contract.offer

    # Contract must be active
    if contract.status != "active":
        return None

    # Escrow must be funded
    if not offer.has_escrow:
        raise ValidationError("Cannot bill session: escrow not funded yet.")

    # Prevent duplicate billing
    if BillingUnit.objects.filter(session=session).exists():
        return None

    tracked_seconds = session.total_seconds
    if tracked_seconds <= 0:
        return None

    # Bill full tracked duration (ignore idle for payment)
    billable_seconds = tracked_seconds
    hourly_rate = offer.agreed_hourly_rate
    billable_hours = Decimal(billable_seconds) / Decimal("3600")
    gross_amount = (billable_hours * hourly_rate).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    # --- New Budget Validation ---
    remaining_budget = offer.remaining_budget
    if remaining_budget <= 0:
        raise ValidationError("Cannot bill session: offer budget exhausted.")

    # Cap the gross_amount to remaining budget
    if gross_amount > remaining_budget:
        gross_amount = remaining_budget
        # Recalculate billable_seconds based on remaining budget
        billable_hours = (gross_amount / hourly_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        billable_seconds = int(billable_hours * 3600)

    return BillingUnit.objects.create(
        contract=contract,
        freelancer=offer.freelancer,
        session=session,
        period_start=session.started_at,
        period_end=session.ended_at,
        billable_seconds=billable_seconds,
        idle_seconds=session.total_idle_seconds,  
        hourly_rate=hourly_rate,
        gross_amount=gross_amount,
        status="pending",
    )




class InvoiceService:

    @staticmethod
    @transaction.atomic
    def create_from_payout(payout: PayoutBatch) -> Invoice:
        """
        Create an immutable invoice from a PAID payout batch.
        """

        if payout.status != "paid":
            raise ValueError("Invoice can only be created for PAID payouts")

        if hasattr(payout, "invoice"):
            raise ValueError("Invoice already exists for this payout")

        invoice = Invoice.objects.create(
            freelancer=payout.freelancer,
            payout_batch=payout,
            total_gross=payout.total_gross,
            platform_fee=payout.platform_fee,
            total_net=payout.total_net,
            issued_at=timezone.now(),
        )

        # Generate invoice number AFTER save (needs ID)
        invoice.invoice_number = InvoiceService._generate_invoice_number(invoice)
        invoice.save(update_fields=["invoice_number"])

        return invoice

    @staticmethod
    def _generate_invoice_number(invoice: Invoice) -> str:
        """
        Example: INV-2026-000123
        """
        year = invoice.issued_at.year
        return f"INV-{year}-{str(invoice.id).split('-')[0].upper()}"
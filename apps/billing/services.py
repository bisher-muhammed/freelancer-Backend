from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.tracking.models import WorkSession
from .models import BillingUnit, Invoice, PayoutBatch

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

    # --- Budget Validation ---
    # Pending (not yet reviewed) units also claim escrow. Counting only
    # approved/locked/paid units (offer.remaining_budget) let several pending
    # sessions each be capped against the same remaining amount, so total
    # billing could exceed the escrow.
    committed = (
        BillingUnit.objects.filter(
            contract=contract,
            status__in=["pending", "approved", "locked", "paid"],
        ).aggregate(total=Sum("gross_amount"))["total"]
        or Decimal("0.00")
    )
    remaining_budget = max(Decimal("0.00"), offer.total_budget - committed)
    if remaining_budget <= 0:
        raise ValidationError("Cannot bill session: offer budget exhausted.")

    # Cap the gross_amount to remaining budget
    if gross_amount > remaining_budget:
        gross_amount = remaining_budget
        # Seconds actually covered by the capped amount (rounded down so the
        # recorded time never exceeds what was paid for)
        billable_seconds = int(
            (gross_amount / hourly_rate * Decimal("3600")).to_integral_value(
                rounding=ROUND_DOWN
            )
        )

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

        payout.refresh_from_db()
        if payout.status != "paid":
            raise RuntimeError("Payout processor failed to mark payout as PAID")

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
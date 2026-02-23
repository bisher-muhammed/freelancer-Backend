from decimal import Decimal
from .models import LedgerEntry

def record_entry(
    *,
    entry_type,
    amount,
    user=None,
    contract=None,
    reference_id=None,
):
    if amount <= 0:
        raise ValueError("Ledger amount must be positive")

    return LedgerEntry.objects.create(
        entry_type=entry_type,
        amount=Decimal(amount),
        user=user,
        contract=contract,
        reference_id=reference_id,
    )

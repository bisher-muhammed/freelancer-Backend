from decimal import Decimal

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Avg, Count

from apps.contract.models import ContractReview


@receiver(post_save, sender=ContractReview)
def update_freelancer_rating(sender, instance, created, **kwargs):
    if not created:
        return

    # Single source of truth for the freelancer's aggregate rating
    freelancer = instance.freelancer  # FreelancerProfile

    stats = ContractReview.objects.filter(
        contract__offer__freelancer=freelancer
    ).aggregate(
        avg=Avg("freelancer_rating"),
        count=Count("id")
    )

    freelancer.average_rating = Decimal(str(round(stats["avg"] or 0, 2)))
    freelancer.total_reviews = stats["count"]
    freelancer.save(update_fields=["average_rating", "total_reviews"])

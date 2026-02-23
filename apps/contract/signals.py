from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Avg, Count

from apps.contract.models import ContractReview


@receiver(post_save, sender=ContractReview)
def update_freelancer_rating(sender, instance, created, **kwargs):
    if not created:
        return

    freelancer = instance.freelancer

    stats = ContractReview.objects.filter(
        contract__offer__freelancer=freelancer.user
    ).aggregate(
        avg=Avg("freelancer_rating"),
        count=Count("id")
    )

    freelancer.average_rating = round(stats["avg"], 2)
    freelancer.total_reviews = stats["count"]
    freelancer.save(update_fields=["average_rating", "total_reviews"])

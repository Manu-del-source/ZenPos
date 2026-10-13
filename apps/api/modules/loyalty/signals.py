"""Connect sales completion and returns to the loyalty ledger.

Sales must not import loyalty (loyalty sits below sales). Signals keep the
dependency pointing the right way.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from modules.sales.models import Sale, SaleReturn


@receiver(post_save, sender=Sale)
def award_points_on_sale(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.status != Sale.Status.COMPLETED:
        return
    # Points follow the money. A cash sale is fully paid at creation and
    # earns here; a sale with unsettled legs (M-Pesa not yet confirmed, a
    # split still owing) earns nothing until the payments module calls the
    # same check when the last leg completes.
    from .services import award_sale_points_if_paid

    award_sale_points_if_paid(instance, actor=instance.cashier)


@receiver(post_save, sender=SaleReturn)
def reverse_points_on_return(sender, instance, **kwargs):
    if instance.status != SaleReturn.Status.COMPLETED:
        return
    from .services import reverse_sale_points

    reverse_sale_points(
        instance.sale, actor=instance.completed_by, reference_id=instance.pk
    )

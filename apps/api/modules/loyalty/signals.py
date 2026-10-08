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
    if instance.payment_method == Sale.PaymentMethod.MPESA:
        # Points wait until the payment completes; the payment service will
        # not call us, so we still award on create for cash and for M-Pesa
        # only once COMPLETED payments exist. Cash sales are completed here.
        pass
    from .services import award_sale_points

    award_sale_points(instance, actor=instance.cashier)


@receiver(post_save, sender=SaleReturn)
def reverse_points_on_return(sender, instance, **kwargs):
    if instance.status != SaleReturn.Status.COMPLETED:
        return
    from .services import reverse_sale_points

    reverse_sale_points(
        instance.sale, actor=instance.completed_by, reference_id=instance.pk
    )

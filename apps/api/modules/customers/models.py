from django.db import models


class Customer(models.Model):
    """A retail customer.

    Organization-scoped: a customer list is a phone book of real people, and one
    shop's staff must not be able to read another shop's. Phones are unique
    *within* an organization rather than globally, because the same person may
    shop at two different businesses — which the pre-phase-4 global unique
    constraint made impossible.

    This keeps its integer key and single ``created_at`` deliberately: phase 8
    rebuilds the model (UUID key, soft deletion, loyalty ledger), and churning
    the primary key now would drag ``Sale`` and the API shape along with it for
    no benefit. ``loyalty_points`` is a mutable balance, which phase 8 replaces
    with a ``loyalty_transactions`` ledger so every points change is explainable.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="customers",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=15, db_index=True)
    loyalty_points = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "phone"],
                name="uniq_customer_org_phone",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.phone})"

from django.db import models

from modules.core.models import BaseModel


class Branch(BaseModel):
    """A physical shop belonging to an organization.

    Branches are first-class: stock, tills, cash sessions, sales and reports all
    hang off a branch, and staff access is granted per branch.

    ``code`` is unique within the organization rather than globally, so two
    organizations can both run a branch called "BR-001".
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="branches",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=32)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["organization__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="uniq_branch_org_code",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

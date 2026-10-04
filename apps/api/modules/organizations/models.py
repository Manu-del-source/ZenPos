from django.db import models

from modules.core.models import BaseModel


class Organization(BaseModel):
    """The retail business. The tenant boundary for every other record.

    One organization may run many branches. Everything that is shared across
    branches - the product catalogue, roles, customers - hangs off this.
    """

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=80, unique=True)
    currency = models.CharField(
        max_length=3,
        default="KES",
        help_text="ISO 4217 code. Kenyan Shilling by default.",
    )
    timezone = models.CharField(max_length=64, default="Africa/Nairobi")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

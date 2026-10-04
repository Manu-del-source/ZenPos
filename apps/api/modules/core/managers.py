from django.db import models
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet whose ``delete()`` marks rows instead of removing them.

    Financial and inventory records must remain explainable, so the default
    delete path must not destroy data. ``hard_delete()`` exists for genuine
    erasure (GDPR-style requests, test teardown) and should be rare.
    """

    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def deleted(self):
        return self.filter(deleted_at__isnull=False)

    def delete(self):
        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Default manager: hides soft-deleted rows.

    Because this is the model's default manager, an accidentally undeleted row
    is invisible to normal queries, which is the safe default for a POS.
    """

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

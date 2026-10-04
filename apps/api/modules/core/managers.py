from django.db import models
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet whose delete() marks rows instead of removing them."""
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def deleted(self):
        return self.filter(deleted_at__isnull=False)

    def delete(self):
        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()


class AllObjectsManager(models.Manager):
    """Unfiltered manager for querying active and soft-deleted records."""
    use_in_migrations = True


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Default manager: hides soft-deleted rows."""
    use_in_migrations = True

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

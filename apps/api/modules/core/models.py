import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from .managers import AllObjectsManager, SoftDeleteManager


class BaseModel(models.Model):
    """UUID primary key plus creation and update timestamps.

    UUID keys are not decoration here. An offline POS terminal must be able to
    create a sale, a customer or a stock movement while it has no network, and
    have that row keep its identity once it reaches the central database. With
    sequential integers that requires a renumbering or mapping step; with UUIDs
    it does not.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteModel(BaseModel):
    """A record that is archived rather than deleted.

    ``objects`` hides archived rows; ``all_objects`` includes them.
    """

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=["deleted_at", "updated_at"])


class AuditLog(BaseModel):
    """One append-only audit row (see ADR-0013).

    Written by ``core.audit.record_audit`` inside the same database
    transaction as the change it describes, so a rolled-back change leaves no
    row and a committed change can never lack one. The log has no update or
    delete path anywhere — including the Django admin.

    The model lives in ``core`` rather than ``accounts`` because every module
    records events, and the import direction rule says a module may only
    import from modules above it: accounts sits below organizations and
    branches, which would make their events unwritable. ``actor`` reaches the
    user model through ``settings.AUTH_USER_MODEL``, which is Django's own
    mechanism for exactly this and is not a business-logic dependency.

    ``before`` and ``after`` are shallow, JSON-safe snapshots; deep diffing is
    a deliberate non-goal for now.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="audit_logs",
        on_delete=models.SET_NULL,
        help_text="Null for events without a session: failed logins record the "
        "attempted username instead.",
    )
    action = models.CharField(max_length=64, db_index=True)
    entity_type = models.CharField(max_length=64, db_index=True)
    entity_id = models.CharField(max_length=64, blank=True, default="")
    branch = models.ForeignKey(
        "branches.Branch",
        null=True,
        blank=True,
        related_name="audit_logs",
        on_delete=models.SET_NULL,
    )
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    attempted_username = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["entity_type", "entity_id"], name="idx_audit_entity"),
            models.Index(fields=["created_at"], name="idx_audit_created_at"),
        ]

    def __str__(self):
        return f"{self.action} by {self.actor} at {self.created_at:%Y-%m-%d %H:%M}"

import uuid

import django.db.models.deletion
from django.conf import settings

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("branches", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("action", models.CharField(db_index=True, max_length=64)),
                ("entity_type", models.CharField(db_index=True, max_length=64)),
                ("entity_id", models.CharField(blank=True, default="", max_length=64)),
                ("before", models.JSONField(blank=True, null=True)),
                ("after", models.JSONField(blank=True, null=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                (
                    "attempted_username",
                    models.CharField(blank=True, default="", max_length=150),
                ),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "branch",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_logs",
                        to="branches.branch",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["entity_type", "entity_id"], name="idx_audit_entity"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["created_at"], name="idx_audit_created_at"),
        ),
    ]

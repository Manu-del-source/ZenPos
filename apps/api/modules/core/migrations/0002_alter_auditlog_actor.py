from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="actor",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Null for events without a session: failed logins record the "
                    "attempted username instead."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="audit_logs",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]

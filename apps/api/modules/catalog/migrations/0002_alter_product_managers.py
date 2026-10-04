import django.db.models.manager
from django.db import migrations

from modules.core.managers import SoftDeleteManager


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.AlterModelManagers(
            name="product",
            managers=[
                ("all_objects", django.db.models.manager.Manager()),
                ("objects", SoftDeleteManager()),
            ],
        ),
    ]

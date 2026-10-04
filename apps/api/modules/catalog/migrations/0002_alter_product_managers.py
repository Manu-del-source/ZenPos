from django.db import migrations

from modules.core.managers import AllObjectsManager, SoftDeleteManager


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.AlterModelManagers(
            name="product",
            managers=[
                ("objects", SoftDeleteManager()),
                ("all_objects", AllObjectsManager()),
            ],
        ),
    ]

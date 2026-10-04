from django.db import migrations

from modules.core.managers import AllObjectsManager, SoftDeleteManager


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
    ]

    # Keep migration state aligned with Product's live custom managers.
    # Both managers opt into migration serialization in core.managers.
    operations = [
        migrations.AlterModelManagers(
            name="product",
            managers=[
                ("objects", SoftDeleteManager()),
                ("all_objects", AllObjectsManager()),
            ],
        ),
    ]

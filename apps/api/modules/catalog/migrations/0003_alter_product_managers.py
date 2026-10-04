from django.db import migrations

from modules.core.managers import AllObjectsManager, SoftDeleteManager


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0002_alter_product_managers"),
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

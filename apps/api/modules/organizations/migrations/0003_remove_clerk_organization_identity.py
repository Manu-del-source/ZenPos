from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0002_clerk_identity"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="organization",
            name="clerk_organization_id",
        ),
    ]

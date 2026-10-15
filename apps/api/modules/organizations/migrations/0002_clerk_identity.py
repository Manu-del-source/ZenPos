from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="clerk_organization_id",
            field=models.CharField(
                blank=True,
                editable=False,
                max_length=255,
                null=True,
                unique=True,
            ),
        ),
    ]

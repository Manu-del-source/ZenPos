from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_expense_permissions"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="clerk_user_id",
            field=models.CharField(
                blank=True,
                editable=False,
                max_length=255,
                null=True,
                unique=True,
            ),
        ),
    ]

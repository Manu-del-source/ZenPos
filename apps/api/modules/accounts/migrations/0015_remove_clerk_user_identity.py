from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0014_seed_hr_manager"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="user",
            name="clerk_user_id",
        ),
    ]

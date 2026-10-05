"""``REFUNDED`` joins the payment status vocabulary.

Voiding a sale that was already paid does not delete the money: the payment row
stays, marked ``REFUNDED``, so reconciliation can see that cash moved back out
and revenue reporting can exclude it. This is a choices-only change.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("COMPLETED", "Completed"),
                    ("FAILED", "Failed"),
                    ("REFUNDED", "Refunded"),
                ],
                db_index=True,
                default="PENDING",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="paymentattempt",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("COMPLETED", "Completed"),
                    ("FAILED", "Failed"),
                    ("REFUNDED", "Refunded"),
                ],
                max_length=10,
            ),
        ),
    ]

"""Settle PENDING M-Pesa payments that nobody polled.

The POS polls a payment's detail to learn its fate, and that poll is the only
thing that asks the provider what happened to an in-flight STK request. If the
register's network drops and the cashier walks away, the payment stays PENDING
and keeps holding stock forever, because no one ever asks again. This command
is the safety net for that case: it sweeps every PENDING M-Pesa payment old
enough to be worth asking about and settles each one through the *same*
``settle_pending_mpesa`` path the poll uses, so a payment gets the same
decision regardless of who is asking.

It is deliberately conservative. For each payment it asks the provider first
(the authority). Only when the provider cannot be asked at all, and the
payment is past the hard timeout, does it fail the payment and release the
stock it was holding. A provider that is reachable and says "still processing"
leaves the payment PENDING for the next sweep.

Run it on a schedule (cron/systemd timer) in production; it is idempotent and
safe to overlap.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from ...models import Payment
from ...services import STK_RECONCILE_AFTER, settle_pending_mpesa


class Command(BaseCommand):
    help = (
        "Ask the provider about every old PENDING M-Pesa payment and settle "
        "the ones it can, releasing stock held by abandoned ones."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be settled without changing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        cutoff = timezone.now() - STK_RECONCILE_AFTER
        stale = (
            Payment.objects.filter(
                method=Payment.Method.MPESA,
                status=Payment.Status.PENDING,
                created_at__lte=cutoff,
            )
            .select_related("sale")
            .order_by("created_at")
        )
        total = stale.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS("No stale PENDING M-Pesa payments."))
            return

        settled = 0
        for payment in stale:
            label = (
                f"payment {payment.pk} (sale {payment.sale.sale_number}, "
                f"{payment.amount} {payment.currency})"
            )
            if dry_run:
                self.stdout.write(f"would settle {label}")
                continue

            before = payment.status
            settle_pending_mpesa(payment=payment, request=None)
            payment.refresh_from_db()
            if payment.status != before:
                settled += 1
                self.stdout.write(
                    f"settled {label}: {before} -> {payment.status}"
                )
            else:
                self.stdout.write(
                    f"left {label} {payment.status} "
                    "(provider still reports it in flight)"
                )

        verb = "Would settle" if dry_run else "Swept"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {total} stale payment(s); {settled} changed state."
            )
        )

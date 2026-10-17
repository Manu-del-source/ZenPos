from django.conf import settings
from django.db import models

from modules.core.models import BaseModel
from modules.sales.models import Sale


class Payment(BaseModel):
    """Money received against a sale.

    ``payments`` is a separate table rather than a column on ``sales``: that is
    what makes split payment, partial payment and per-method reconciliation
    possible. The ``sale`` foreign key is PROTECT — a payment must survive the
    phase-6 rebuild of ``Sale``, and a payment that outlives its sale would be
    unexplainable money.

    Only a verified provider callback transitions ``status`` from PENDING to
    COMPLETED — never a client message (security rule 4). ``received_by`` is
    nullable because a callback arrives without a user session.
    """

    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        MPESA = "MPESA", "M-Pesa"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
        REFUNDED = "REFUNDED", "Refunded"

    sale = models.ForeignKey(
        Sale,
        related_name="payments",
        on_delete=models.PROTECT,
    )
    method = models.CharField(max_length=10, choices=Method.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="KES")
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    # The provider's receipt number, e.g. the M-Pesa TransactionID. Empty for
    # cash and for M-Pesa payments still awaiting the callback.
    provider_reference = models.CharField(max_length=64, blank=True, default="")
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="payments_received",
        on_delete=models.PROTECT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.method} {self.amount} {self.currency} ({self.status})"


class PaymentAttempt(BaseModel):
    """One exchange with a payment provider on behalf of a payment.

    The full request and response payloads are kept so reconciliation can
    answer what was actually asked of the provider and what it said — the
    sales domain records only *that* money moved, never *how* (ADR-0012).
    """

    payment = models.ForeignKey(
        Payment,
        related_name="attempts",
        on_delete=models.PROTECT,
    )
    attempt_number = models.PositiveIntegerField()
    provider = models.CharField(max_length=20)
    # The provider's request id for this attempt. The callback handler matches
    # on this column: a JSON payload search would be both slower and fragile.
    checkout_request_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    request_payload = models.JSONField()
    response_payload = models.JSONField()
    # What was actually sent to the provider. M-Pesa STK push charges whole
    # shillings only, so this can differ from ``payment.amount`` by the
    # rounding — reconciliation must be able to explain that difference.
    provider_amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=10, choices=Payment.Status.choices)
    error = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["payment", "attempt_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["payment", "attempt_number"],
                name="uniq_payment_attempt_number",
            ),
        ]

    def __str__(self):
        return f"{self.provider} attempt {self.attempt_number} ({self.status})"


class WebhookEvent(BaseModel):
    """A received provider callback, stored for idempotency.

    The unique ``(provider, external_id)`` pair *is* the idempotency guard: a
    redelivered M-Pesa callback loses the insert race, matches the unique
    constraint, and is answered 200 without re-effecting anything. Callbacks
    for unknown ``CheckoutRequestID``s are never stored here with success
    semantics (ADR-0012).
    """

    provider = models.CharField(max_length=20, db_index=True)
    external_id = models.CharField(max_length=64, db_index=True)
    payload = models.JSONField()
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "external_id"],
                name="uniq_webhook_provider_external_id",
            ),
        ]

    def __str__(self):
        return f"{self.provider}:{self.external_id}"


class MerchantTillAccount(models.Model):
    """A merchant shortcode registered to one ZenPOS organization/branch.

    C2B callbacks are routed by shortcode, never by a client-supplied tenant ID.
    """
    class Environment(models.TextChoices):
        SANDBOX = "sandbox", "Sandbox"
        PRODUCTION = "production", "Production"

    organization = models.ForeignKey(
        "organizations.Organization", related_name="mpesa_till_accounts",
        on_delete=models.PROTECT,
    )
    branch = models.ForeignKey(
        "branches.Branch", related_name="mpesa_till_accounts",
        null=True, blank=True, on_delete=models.PROTECT,
    )
    shortcode = models.CharField(max_length=32)
    environment = models.CharField(max_length=12, choices=Environment.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["organization__name", "shortcode"]
        constraints = [
            models.UniqueConstraint(
                fields=["shortcode", "environment"],
                name="uniq_mpesa_shortcode_environment",
            ),
        ]

    def __str__(self):
        return f"{self.shortcode} ({self.environment})"


class IncomingTillTransaction(models.Model):
    """Verified C2B money received by a merchant, awaiting sale assignment."""
    class Status(models.TextChoices):
        UNMATCHED = "UNMATCHED", "Unmatched"
        MATCHED = "MATCHED", "Matched"
        DUPLICATE_REVIEW = "DUPLICATE_REVIEW", "Duplicate review"
        REJECTED = "REJECTED", "Rejected"

    account = models.ForeignKey(
        MerchantTillAccount, related_name="transactions", on_delete=models.PROTECT,
    )
    receipt_number = models.CharField(max_length=64)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="KES")
    transaction_time = models.DateTimeField()
    payer_phone = models.CharField(max_length=32, blank=True, default="")
    payer_first_name = models.CharField(max_length=80, blank=True, default="")
    payer_middle_name = models.CharField(max_length=80, blank=True, default="")
    payer_last_name = models.CharField(max_length=80, blank=True, default="")
    bill_reference = models.CharField(max_length=64, blank=True, default="")
    third_party_transaction_id = models.CharField(max_length=64, blank=True, default="")
    raw_payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNMATCHED, db_index=True)
    matched_sale = models.ForeignKey(
        "sales.Sale", related_name="matched_till_transactions",
        null=True, blank=True, on_delete=models.PROTECT,
    )
    matched_payment = models.OneToOneField(
        Payment, related_name="matched_till_transaction",
        null=True, blank=True, on_delete=models.PROTECT,
    )
    matched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        related_name="matched_till_transactions", on_delete=models.PROTECT,
    )
    matched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-transaction_time", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "receipt_number"],
                name="uniq_till_receipt_per_account",
            ),
        ]
        indexes = [
            models.Index(fields=["account", "status", "transaction_time"], name="idx_till_txn_queue"),
        ]

    def __str__(self):
        return f"{self.receipt_number} — {self.amount} {self.currency}"

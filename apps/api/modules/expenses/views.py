from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils.dateparse import parse_date
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from modules.core.audit import record_audit, snapshot
from modules.core.mixins import BranchScopedMixin, OrganizationScopedMixin

from .models import Expense, ExpenseCategory
from .serializers import ExpenseCategorySerializer, ExpenseSerializer
from .services import reverse_expense


class ExpenseCategoryViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    """Cost buckets for the tenant.

    Reading a category is an ``expenses.view`` act — anyone who may record or
    review spend needs the vocabulary. Creating, retiring or removing a
    category is ``expenses.manage``: it shapes how the tenant's money is
    reported.
    """

    queryset = ExpenseCategory.objects.select_related("organization")
    serializer_class = ExpenseCategorySerializer

    required_permissions = ("expenses.view",)
    required_permissions_by_action = {
        "create": ("expenses.manage",),
        "update": ("expenses.manage",),
        "partial_update": ("expenses.manage",),
        "destroy": ("expenses.manage",),
    }

    def perform_create(self, serializer):
        with transaction.atomic():
            super().perform_create(serializer)
            record_audit(
                action="expense_category.created",
                entity_type="expense_category",
                entity_id=serializer.instance.pk,
                actor=self.request.user,
                request=self.request,
                after=snapshot(serializer.instance),
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            before = snapshot(serializer.instance)
            super().perform_update(serializer)
            record_audit(
                action="expense_category.updated",
                entity_type="expense_category",
                entity_id=serializer.instance.pk,
                actor=self.request.user,
                request=self.request,
                before=before,
                after=snapshot(serializer.instance),
            )

    def perform_destroy(self, instance):
        before = snapshot(instance)
        try:
            with transaction.atomic():
                instance.delete()
                record_audit(
                    action="expense_category.deleted",
                    entity_type="expense_category",
                    entity_id=before.get("id"),
                    actor=self.request.user,
                    request=self.request,
                    before=before,
                )
        except ProtectedError as error:
            # The category still has expenses pointing at it. The correct move
            # is to deactivate it; the money rows must keep their vocabulary.
            raise ValidationError(
                "That category still has expenses. Deactivate it instead of deleting it."
            ) from error


class ExpenseViewSet(
    BranchScopedMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Money out, append-only.

    There is deliberately no update and no delete: the only correction is a
    reversal row (``reverse``), and that is on purpose (ADR-0015) — a figure
    must always explain itself from the rows that built it. The queryset is
    branch-scoped like the till, so a user posted to one branch never reads
    another branch's spend, and ``BranchScopedMixin`` also refuses to create
    an expense in a branch the caller is not posted to.
    """

    queryset = Expense.objects.select_related(
        "organization", "branch", "category", "created_by", "reversal_of"
    )
    serializer_class = ExpenseSerializer
    branch_field = "branch"

    required_permissions = ("expenses.view",)
    required_permissions_by_action = {
        "create": ("expenses.manage",),
        "reverse": ("expenses.manage",),
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        date_from = parse_date(params.get("date_from", "") or "")
        date_to = parse_date(params.get("date_to", "") or "")
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
        if params.get("category"):
            queryset = queryset.filter(category_id=params["category"])
        return queryset

    def perform_create(self, serializer):
        with transaction.atomic():
            super().perform_create(serializer)
            expense = serializer.instance
            record_audit(
                action="expense.created",
                entity_type="expense",
                entity_id=expense.pk,
                actor=self.request.user,
                request=self.request,
                branch=expense.branch,
                after=snapshot(expense),
            )

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        """Correct an expense without touching it: append a reversal row."""
        expense = self.get_object()
        reversal = reverse_expense(expense=expense, actor=request.user, request=request)
        serializer = self.get_serializer(reversal)
        return Response(serializer.data, status=201)

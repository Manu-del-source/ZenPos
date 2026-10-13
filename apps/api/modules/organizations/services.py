"""Tenant onboarding: the only API path that creates an organization.

A new tenant must be usable the moment it exists, so the organization, its
first branch and its first administrator are one atomic fact, and the audit
row says who opened it. Everything a tenant needs beyond that (catalogue,
staff, settings) is built by the tenant's own administrator.
"""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as CoreValidationError
from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from modules.accounts.models import Role, User, UserRole
from modules.branches.models import Branch
from modules.core.audit import record_audit

from .models import Organization


def onboard_organization(
    *,
    name,
    slug,
    currency,
    timezone,
    branch_name,
    branch_code,
    admin_username,
    admin_password,
    admin_email="",
    actor=None,
    request=None,
) -> Organization:
    """Create an organization with its first branch and administrator.

    Raises ``ValidationError`` (a 400) for a slug or username that is taken,
    or a password that fails the platform's validators. All three rows commit
    together, so a failure leaves no half-open tenant behind.
    """
    if Organization.objects.filter(slug=slug).exists():
        raise ValidationError({"slug": "An organization with this slug already exists."})
    if User.objects.filter(username=admin_username).exists():
        raise ValidationError({"admin_username": "A user with this username already exists."})
    try:
        validate_password(admin_password)
    except CoreValidationError as exc:
        raise ValidationError({"admin_password": exc.messages}) from exc

    with transaction.atomic():
        try:
            organization = Organization.objects.create(
                name=name, slug=slug, currency=currency, timezone=timezone
            )
        except IntegrityError:
            # Two onboarding calls raced on the slug; the pre-check above
            # cannot cover that, the unique constraint is the authority.
            raise ValidationError(
                {"slug": "An organization with this slug already exists."}
            ) from None

        branch = Branch.objects.create(
            organization=organization, name=branch_name, code=branch_code
        )
        user = User.objects.create_user(
            username=admin_username,
            password=admin_password,
            email=admin_email,
            organization=organization,
            is_staff=True,
        )
        admin_role = Role.objects.get(name="ADMIN", organization__isnull=True)
        UserRole.objects.create(user=user, role=admin_role)

        record_audit(
            action="organization.created",
            entity_type="organization",
            entity_id=organization.pk,
            actor=actor,
            request=request,
            after={
                "name": organization.name,
                "slug": organization.slug,
                "first_branch": str(branch.pk),
                "first_admin": admin_username,
            },
        )
    return organization

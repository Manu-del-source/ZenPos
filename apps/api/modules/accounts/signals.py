"""Auth-signal receivers that write audit rows.

Connected in ``AccountsConfig.ready``. Login success and failure are the two
auth events in the phase-5 audit scope; token refresh is deliberately not
logged — it has no state change and would only add noise.
"""

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from modules.core.audit import record_audit


@receiver(user_logged_in)
def audit_login(sender, request, user, **kwargs):
    record_audit(
        action="auth.login",
        entity_type="user",
        entity_id=user.pk,
        actor=user,
        request=request,
    )


@receiver(user_login_failed)
def audit_login_failed(sender, credentials, request=None, **kwargs):
    """A failed attempt has no session, so the actor is null by design.

    The attempted username is what makes the row useful: it is the evidence a
    password-guessing run leaves behind. The login throttle (10/min per
    address) bounds how many of these an attacker can generate.
    """
    record_audit(
        action="auth.login_failed",
        entity_type="user",
        actor=None,
        request=request,
        attempted_username=(credentials or {}).get("username", ""),
    )

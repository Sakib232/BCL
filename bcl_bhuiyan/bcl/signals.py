"""Authentication audit events and candidate profile / is_active synchronization signals."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_save, pre_delete, post_delete
from django.dispatch import receiver
from .privacy import audit
from .models import CandidateProfile

User = get_user_model()


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    audit('auth.login', actor=user)


@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    if user and user.pk:
        audit('auth.logout', actor=user)


@receiver(user_login_failed)
def log_failed_login(sender, credentials, request, **kwargs):
    audit('auth.login_failed', outcome='denied')


@receiver(post_save, sender=CandidateProfile)
def sync_candidate_profile_to_user(sender, instance, created, **kwargs):
    """
    Ensure User.is_active is synchronized with CandidateProfile.status.
    Approved -> is_active = True
    Pending / Rejected -> is_active = False
    """
    if getattr(instance, "_syncing_status", False):
        return

    user = instance.user
    if not user:
        return

    target_active = (instance.status == CandidateProfile.ApprovalStatus.APPROVED)
    if user.is_active != target_active:
        user.is_active = target_active
        user._syncing_status = True
        try:
            user.save(update_fields=["is_active"])
        finally:
            user._syncing_status = False


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def on_user_saved(sender, instance, created, **kwargs):
    """
    1. When a user is created in Django (e.g. from main auth.User admin),
       trigger creation of a CandidateProfile so every candidate is registered in Candidate Approvals.
    2. When an existing user's is_active changes, sync CandidateProfile status.
    """
    if getattr(instance, "_syncing_status", False):
        return

    if created:
        # Superusers and staff/subadmins do not receive automatic candidate profiles
        if instance.is_superuser or instance.is_staff:
            return

        # Create candidate profile if one was not already created by the registration/add form
        if not CandidateProfile.objects.filter(user=instance).exists():
            status = (
                CandidateProfile.ApprovalStatus.APPROVED
                if instance.is_active
                else CandidateProfile.ApprovalStatus.PENDING
            )
            CandidateProfile.objects.create(
                user=instance,
                Mock_from="BCL_Bhuiyan",
                status=status,
            )
    else:
        try:
            profile = instance.candidate_profile
        except (CandidateProfile.DoesNotExist, AttributeError):
            return

        if instance.is_active and profile.status != CandidateProfile.ApprovalStatus.APPROVED:
            profile.status = CandidateProfile.ApprovalStatus.APPROVED
            profile._syncing_status = True
            try:
                profile.save(update_fields=["status", "updated_at"])
            finally:
                profile._syncing_status = False
        elif not instance.is_active and profile.status == CandidateProfile.ApprovalStatus.APPROVED:
            profile.status = CandidateProfile.ApprovalStatus.PENDING
            profile._syncing_status = True
            try:
                profile.save(update_fields=["status", "updated_at"])
            finally:
                profile._syncing_status = False


@receiver(pre_delete, sender=settings.AUTH_USER_MODEL)
def mark_user_being_deleted(sender, instance, **kwargs):
    instance._is_being_deleted = True


@receiver(post_delete, sender=CandidateProfile)
def delete_user_on_candidate_profile_delete(sender, instance, **kwargs):
    """
    When a CandidateProfile is deleted, also delete the associated auth.User.
    """
    try:
        user = instance.user
    except (User.DoesNotExist, AttributeError):
        return

    if user and not getattr(user, "_is_being_deleted", False):
        user._is_being_deleted = True
        try:
            from .models import CandidateAttempt, FullMockAttempt
            FullMockAttempt.objects.filter(candidate=user).delete()
            CandidateAttempt.objects.filter(candidate=user).delete()
            user.delete()
        except Exception:
            pass

"""
Celery tasks — Smart Nudge Engine (roadmap Module 7).

Scheduled tasks (add to CELERY_BEAT_SCHEDULE in settings):
  - send_contribution_reminders   every day at 08:00 EAT
  - send_overdue_alerts           every day at 09:00 EAT
  - send_reengagement_nudges      every Monday at 09:00 EAT
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import Notification
from .service import send_notification

logger = logging.getLogger(__name__)


@shared_task
def send_contribution_reminders():
    """
    3 days before a cycle's due_date → send reminder to members who haven't paid yet.
    """
    from contributions.models import Contribution, ContributionCycle

    target_date = (timezone.now() + timedelta(days=3)).date()
    upcoming_cycles = ContributionCycle.objects.filter(due_date=target_date, is_closed=False)

    for cycle in upcoming_cycles:
        unpaid = Contribution.objects.filter(
            cycle=cycle,
            status=Contribution.STATUS_PENDING,
        ).select_related('member__user', 'cycle__group')

        for contribution in unpaid:
            user = contribution.member.user
            group_name = cycle.group.name

            send_notification(
                user=user,
                notification_type=Notification.TYPE_CONTRIBUTION_REMINDER,
                title=f"Contribution due in 3 days — {group_name}",
                body=f"Your contribution for {group_name} (Cycle {cycle.cycle_number}) is due on {cycle.due_date}. Tap to pay now.",
                sms_body=f"T-Cash: Your {group_name} contribution is due on {cycle.due_date}. Log in to pay.",
                metadata={'group_id': cycle.group_id, 'cycle_id': cycle.id},
            )

    logger.info("Contribution reminders sent for %s cycles due on %s.", upcoming_cycles.count(), target_date)


@shared_task
def send_overdue_alerts():
    """
    1 day after due_date → urgent alert for still-unpaid contributions.
    Also marks overdue contributions as LATE (streak reset handled by mark_paid).
    """
    from contributions.models import Contribution, ContributionCycle

    yesterday = (timezone.now() - timedelta(days=1)).date()
    overdue_cycles = ContributionCycle.objects.filter(due_date=yesterday, is_closed=False)

    for cycle in overdue_cycles:
        unpaid = Contribution.objects.filter(
            cycle=cycle,
            status=Contribution.STATUS_PENDING,
        ).select_related('member__user', 'cycle__group')

        for contribution in unpaid:
            user = contribution.member.user
            group_name = cycle.group.name

            send_notification(
                user=user,
                notification_type=Notification.TYPE_CONTRIBUTION_OVERDUE,
                title=f"Overdue contribution — {group_name}",
                body=f"Your contribution for {group_name} (Cycle {cycle.cycle_number}) was due yesterday. Pay now to protect your streak.",
                sms_body=f"T-Cash: Your {group_name} contribution is overdue. Pay now to avoid a missed mark.",
                metadata={'group_id': cycle.group_id, 'cycle_id': cycle.id},
            )

    logger.info("Overdue alerts sent for %s cycles.", overdue_cycles.count())


@shared_task
def mark_missed_contributions():
    """
    Close cycles that are >7 days overdue and mark all remaining PENDING as MISSED.
    Triggered by Celery Beat — runs daily.
    """
    from contributions.models import Contribution, ContributionCycle

    cutoff = (timezone.now() - timedelta(days=7)).date()
    stale_cycles = ContributionCycle.objects.filter(due_date__lt=cutoff, is_closed=False)

    for cycle in stale_cycles:
        missed = Contribution.objects.filter(cycle=cycle, status=Contribution.STATUS_PENDING)
        for contribution in missed:
            contribution.status = Contribution.STATUS_MISSED
            contribution.save(update_fields=['status'])
            # Reset streak — same logic as late payment
            member = contribution.member
            member.contribution_streak = 0
            member.save(update_fields=['contribution_streak'])

        cycle.is_closed = True
        cycle.save(update_fields=['is_closed'])

    logger.info("Closed %s overdue cycles and marked missed contributions.", stale_cycles.count())


@shared_task
def send_reengagement_nudges():
    """
    Re-engagement: members who haven't logged in for 14+ days get a nudge.
    Uses last_login from the User model.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    cutoff = timezone.now() - timedelta(days=14)
    inactive_users = User.objects.filter(
        last_login__lt=cutoff,
        is_active=True,
    )

    for user in inactive_users:
        send_notification(
            user=user,
            notification_type=Notification.TYPE_GENERAL,
            title="We miss you on T-Cash!",
            body="Your group is saving without you. Log in to check your contributions and stay on track.",
            sms_body="T-Cash: Your group has been active. Log in to stay on track with your savings.",
            channels=[Notification.CHANNEL_PUSH, Notification.CHANNEL_SMS],
        )

    logger.info("Re-engagement nudges sent to %s inactive users.", inactive_users.count())


@shared_task
def notify_withdrawal_signatories(withdrawal_request_id: int):
    """
    Notify all signatories + admin when a new withdrawal request is created.
    Called from groups/views.py after WithdrawalRequest is created.
    """
    from groups.models import GroupMember, WithdrawalRequest

    try:
        wr = WithdrawalRequest.objects.select_related('group', 'requested_by').get(id=withdrawal_request_id)
    except WithdrawalRequest.DoesNotExist:
        return

    signatories = GroupMember.objects.filter(
        group=wr.group,
        status=GroupMember.STATUS_ACTIVE,
        role__in=[GroupMember.ROLE_SIGNATORY, GroupMember.ROLE_ADMIN],
    ).exclude(user=wr.requested_by).select_related('user')

    for m in signatories:
        send_notification(
            user=m.user,
            notification_type=Notification.TYPE_WITHDRAWAL_VOTE,
            title=f"Withdrawal approval needed — {wr.group.name}",
            body=f"{wr.requested_by.phone_number} has requested a withdrawal. Your vote is required.",
            sms_body=f"T-Cash: A withdrawal request in {wr.group.name} needs your approval. Log in to vote.",
            metadata={'group_id': wr.group_id, 'withdrawal_request_id': wr.id},
        )


@shared_task
def notify_member_joined(group_id: int, user_id: int):
    """Notify group admin when a new member requests to join."""
    from django.contrib.auth import get_user_model
    from groups.models import Group, GroupMember

    User = get_user_model()
    try:
        group = Group.objects.get(id=group_id)
        user = User.objects.get(id=user_id)
    except (Group.DoesNotExist, User.DoesNotExist):
        return

    admin = GroupMember.objects.filter(
        group=group, role=GroupMember.ROLE_ADMIN, status=GroupMember.STATUS_ACTIVE
    ).select_related('user').first()

    if admin:
        send_notification(
            user=admin.user,
            notification_type=Notification.TYPE_MEMBER_JOINED,
            title=f"New join request — {group.name}",
            body=f"{user.phone_number} has requested to join {group.name}. Tap to approve or reject.",
            sms_body=f"T-Cash: {user.phone_number} wants to join {group.name}. Log in to approve.",
            metadata={'group_id': group_id, 'user_id': user_id},
        )


@shared_task
def notify_contribution_confirmed(contribution_id: int):
    """
    Notify member + group admin after a contribution is confirmed via M-Pesa callback.
    Called from contributions/views.py after successful webhook processing.
    """
    from contributions.models import Contribution
    from groups.models import GroupMember

    try:
        contribution = Contribution.objects.select_related(
            'member__user', 'cycle__group'
        ).get(id=contribution_id)
    except Contribution.DoesNotExist:
        return

    user = contribution.member.user
    group = contribution.cycle.group

    # Notify the member
    send_notification(
        user=user,
        notification_type=Notification.TYPE_CONTRIBUTION_CONFIRMED,
        title=f"Contribution received — {group.name}",
        body=f"Your contribution for {group.name} (Cycle {contribution.cycle.cycle_number}) has been received. Streak: {contribution.member.contribution_streak}.",
        sms_body=f"T-Cash: Your contribution to {group.name} has been received. Thank you!",
        metadata={'group_id': group.id, 'contribution_id': contribution.id},
    )

    # Notify the group admin
    admin = GroupMember.objects.filter(
        group=group, role=GroupMember.ROLE_ADMIN, status=GroupMember.STATUS_ACTIVE
    ).select_related('user').first()

    if admin and admin.user != user:
        send_notification(
            user=admin.user,
            notification_type=Notification.TYPE_CONTRIBUTION_CONFIRMED,
            title=f"Payment received — {group.name}",
            body=f"{user.phone_number} has made their contribution for Cycle {contribution.cycle.cycle_number}.",
            sms_body=None,  # no SMS to admin for individual contributions
            channels=[Notification.CHANNEL_IN_APP, Notification.CHANNEL_PUSH],
            metadata={'group_id': group.id, 'contribution_id': contribution.id},
        )
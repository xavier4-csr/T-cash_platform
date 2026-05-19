from django.conf import settings
from django.db import models
from django.utils import timezone


class ContributionCycle(models.Model):
    """
    Represents one contribution cycle for a group (e.g. April 2026).
    Members are expected to pay exactly group.contribution_amount by due_date.
    """
    group = models.ForeignKey(
        'groups.Group', on_delete=models.CASCADE, related_name='cycles'
    )
    cycle_number = models.PositiveIntegerField()          # 1, 2, 3 ...
    due_date = models.DateField()
    is_closed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('group', 'cycle_number')
        ordering = ['cycle_number']

    def __str__(self):
        return f"{self.group.name} — Cycle {self.cycle_number} (due {self.due_date})"


class Contribution(models.Model):
    """
    Immutable record of a single contribution payment by a member.
    Created only after M-Pesa callback is validated.
    """
    STATUS_PENDING = 'PENDING'        # STK Push sent, awaiting callback
    STATUS_PAID = 'PAID'              # On time
    STATUS_LATE = 'LATE'              # Paid after due date
    STATUS_MISSED = 'MISSED'          # Cycle closed, never paid
    STATUS_REVERSED = 'REVERSED'      # Multi-sig reversal applied
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PAID, 'Paid'),
        (STATUS_LATE, 'Late'),
        (STATUS_MISSED, 'Missed'),
        (STATUS_REVERSED, 'Reversed'),
    ]

    cycle = models.ForeignKey(ContributionCycle, on_delete=models.PROTECT, related_name='contributions')
    member = models.ForeignKey(
        'groups.GroupMember', on_delete=models.PROTECT, related_name='contributions'
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)

    # M-Pesa reference — idempotency key (duplicate callbacks ignored)
    mpesa_reference = models.CharField(max_length=50, unique=True, null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('cycle', 'member')   # one contribution record per member per cycle

    def mark_paid(self, mpesa_ref, paid_at=None):
        """
        Called from the M-Pesa callback webhook after signature validation.
        Determines PAID vs LATE based on cycle due_date.
        Records are immutable after this point — no further edits.
        """
        self.mpesa_reference = mpesa_ref
        self.paid_at = paid_at or timezone.now()
        due = self.cycle.due_date
        self.status = self.STATUS_PAID if self.paid_at.date() <= due else self.STATUS_LATE
        self.save(update_fields=['mpesa_reference', 'paid_at', 'status'])

        # Update streak on the GroupMember
        self._update_streak()

    def _update_streak(self):
        member = self.member
        if self.status == self.STATUS_PAID:
            member.contribution_streak += 1
        else:
            member.contribution_streak = 0   # LATE resets streak
        member.save(update_fields=['contribution_streak'])

        # Award badges at milestones
        Badge.award_if_eligible(member)

    def __str__(self):
        return f"{self.member} — {self.cycle} [{self.status}]"


class ContributionReversal(models.Model):
    """
    Reversal record for a contribution — requires admin + treasurer approval.
    The original Contribution is never deleted or edited.
    """
    STATUS_PENDING = 'PENDING'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    contribution = models.OneToOneField(
        Contribution, on_delete=models.PROTECT, related_name='reversal'
    )
    reason = models.TextField()
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='reversal_requests'
    )
    approved_by_admin = models.BooleanField(default=False)
    approved_by_treasurer = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def check_approval(self):
        """Approve once both admin and treasurer have signed off."""
        if self.approved_by_admin and self.approved_by_treasurer:
            self.status = self.STATUS_APPROVED
            self.resolved_at = timezone.now()
            # Mark original contribution reversed
            self.contribution.status = Contribution.STATUS_REVERSED
            self.contribution.save(update_fields=['status'])
            self.save(update_fields=['status', 'resolved_at'])
        else:
            self.save(update_fields=['approved_by_admin', 'approved_by_treasurer'])

    def __str__(self):
        return f"Reversal for {self.contribution} [{self.status}]"


class RotationSchedule(models.Model):
    """
    Tracks the merry-go-round payout order for rotating-type groups.
    Each slot maps a position to a GroupMember and whether they've received the pool.
    """
    group = models.ForeignKey(
        'groups.Group', on_delete=models.CASCADE, related_name='rotation_schedule'
    )
    cycle = models.ForeignKey(
        ContributionCycle, on_delete=models.CASCADE, related_name='rotation_slots'
    )
    member = models.ForeignKey(
        'groups.GroupMember', on_delete=models.PROTECT, related_name='rotation_slots'
    )
    position = models.PositiveIntegerField()          # 1-based payout order
    has_received = models.BooleanField(default=False)
    received_at = models.DateTimeField(null=True, blank=True)
    skipped = models.BooleanField(default=False)      # missed contribution → skip this cycle

    class Meta:
        unique_together = ('group', 'cycle', 'position')
        ordering = ['position']

    def mark_received(self):
        self.has_received = True
        self.received_at = timezone.now()
        self.save(update_fields=['has_received', 'received_at'])

    def __str__(self):
        return f"{self.group.name} Cycle {self.cycle.cycle_number} Position {self.position} → {self.member}"


class Badge(models.Model):
    """
    Gamification badges awarded to members for contribution milestones.
    Milestones: 3, 6, 12 consecutive on-time contributions.
    """
    BADGE_3 = 'STREAK_3'
    BADGE_6 = 'STREAK_6'
    BADGE_12 = 'STREAK_12'
    BADGE_CHOICES = [
        (BADGE_3, '3-Month Streak 🔥'),
        (BADGE_6, '6-Month Streak ⭐'),
        (BADGE_12, '12-Month Streak 🏆'),
    ]
    MILESTONES = {3: BADGE_3, 6: BADGE_6, 12: BADGE_12}

    member = models.ForeignKey(
        'groups.GroupMember', on_delete=models.CASCADE, related_name='badges'
    )
    badge_type = models.CharField(max_length=20, choices=BADGE_CHOICES)
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('member', 'badge_type')

    @classmethod
    def award_if_eligible(cls, group_member):
        streak = group_member.contribution_streak
        badge_type = cls.MILESTONES.get(streak)
        if badge_type:
            cls.objects.get_or_create(member=group_member, badge_type=badge_type)

    def __str__(self):
        return f"{self.member} — {self.get_badge_type_display()}"
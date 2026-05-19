import random
import string
from django.conf import settings
from django.db import models
from django.utils import timezone


def generate_group_code():
    """Generate a unique 6-character alphanumeric group invite code."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


class Group(models.Model):
    """
    A chama / savings group.
    Supports three types: rotating pool (merry-go-round), fixed pool, investment club.
    """

    TYPE_ROTATING = 'ROTATING'
    TYPE_FIXED = 'FIXED'
    TYPE_INVESTMENT = 'INVESTMENT'
    GROUP_TYPE_CHOICES = [
        (TYPE_ROTATING, 'Rotating (Merry-Go-Round)'),
        (TYPE_FIXED, 'Fixed Pool'),
        (TYPE_INVESTMENT, 'Investment Club'),
    ]

    FREQUENCY_WEEKLY = 'WEEKLY'
    FREQUENCY_MONTHLY = 'MONTHLY'
    FREQUENCY_CHOICES = [
        (FREQUENCY_WEEKLY, 'Weekly'),
        (FREQUENCY_MONTHLY, 'Monthly'),
    ]

    STATUS_ACTIVE = 'ACTIVE'
    STATUS_PAUSED = 'PAUSED'
    STATUS_CLOSED = 'CLOSED'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_PAUSED, 'Paused'),
        (STATUS_CLOSED, 'Closed'),
    ]

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    group_type = models.CharField(max_length=20, choices=GROUP_TYPE_CHOICES, default=TYPE_ROTATING)
    group_code = models.CharField(max_length=6, unique=True, default=generate_group_code)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)

    # Contribution rules
    contribution_amount = models.DecimalField(max_digits=12, decimal_places=2)
    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES, default=FREQUENCY_MONTHLY)
    max_members = models.PositiveIntegerField(default=20)

    # Withdrawal governance — how many signatories must approve
    withdrawal_quorum = models.PositiveIntegerField(
        default=2,
        help_text='Number of signatory approvals required to authorise a withdrawal.'
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_groups',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def member_count(self):
        return self.memberships.filter(status=GroupMember.STATUS_ACTIVE).count()

    def is_full(self):
        return self.member_count() >= self.max_members

    def invalidate_code(self):
        """Invalidate the invite code once group is full."""
        self.group_code = 'CLOSED'
        self.save(update_fields=['group_code'])

    def __str__(self):
        return f"{self.name} ({self.group_code})"


class GroupMember(models.Model):
    """
    Membership record linking a User to a Group with a role.
    """
    ROLE_ADMIN = 'ADMIN'
    ROLE_TREASURER = 'TREASURER'
    ROLE_SIGNATORY = 'SIGNATORY'
    ROLE_MEMBER = 'MEMBER'
    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Admin'),
        (ROLE_TREASURER, 'Treasurer'),
        (ROLE_SIGNATORY, 'Signatory'),
        (ROLE_MEMBER, 'Member'),
    ]

    STATUS_PENDING = 'PENDING'
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_REJECTED = 'REJECTED'
    STATUS_LEFT = 'LEFT'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Approval'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_LEFT, 'Left'),
    ]

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    joined_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Contribution streak — updated by contributions module
    contribution_streak = models.IntegerField(default=0)

    class Meta:
        unique_together = ('group', 'user')

    def activate(self):
        self.status = self.STATUS_ACTIVE
        self.joined_at = timezone.now()
        self.save(update_fields=['status', 'joined_at'])

    def __str__(self):
        return f"{self.user.phone_number} in {self.group.name} ({self.role})"


class GroupAuditLog(models.Model):
    """
    Immutable log of all significant group actions.
    Actor, action, timestamp — required for financial governance.
    """
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='audit_logs')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='group_audit_actions',
    )
    action = models.CharField(max_length=100)   # e.g. 'RULE_CHANGED', 'MEMBER_APPROVED'
    detail = models.JSONField(default=dict)      # flexible payload
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.group.name} — {self.action}"


class WithdrawalRequest(models.Model):
    """
    Multi-signature withdrawal governance.
    A request must collect `group.withdrawal_quorum` APPROVE votes before
    funds are disbursed. A single REJECT vote flags it for admin review.
    """
    STATUS_PENDING = 'PENDING'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_FLAGGED = 'FLAGGED'
    STATUS_DISBURSED = 'DISBURSED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_FLAGGED, 'Flagged for Review'),
        (STATUS_DISBURSED, 'Disbursed'),
    ]

    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name='withdrawal_requests')
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='withdrawal_requests',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def approve_count(self):
        return self.votes.filter(vote=WithdrawalVote.VOTE_APPROVE).count()

    def has_rejection(self):
        return self.votes.filter(vote=WithdrawalVote.VOTE_REJECT).exists()

    def check_quorum(self):
        """
        Called after each new vote.
        - If a rejection exists → flag for admin review.
        - If approval count reaches quorum → mark APPROVED (triggers payment).
        - Admin requesting their own withdrawal is blocked at the view level.
        """
        if self.has_rejection():
            self.status = self.STATUS_FLAGGED
        elif self.approve_count() >= self.group.withdrawal_quorum:
            self.status = self.STATUS_APPROVED
        self.save(update_fields=['status'])
        return self.status

    def __str__(self):
        return f"Withdrawal KES {self.amount} from {self.group.name} [{self.status}]"


class WithdrawalVote(models.Model):
    """
    Individual signatory vote on a withdrawal request.
    """
    VOTE_APPROVE = 'APPROVE'
    VOTE_REJECT = 'REJECT'
    VOTE_CHOICES = [
        (VOTE_APPROVE, 'Approve'),
        (VOTE_REJECT, 'Reject'),
    ]

    request = models.ForeignKey(WithdrawalRequest, on_delete=models.CASCADE, related_name='votes')
    voter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='withdrawal_votes',
    )
    vote = models.CharField(max_length=10, choices=VOTE_CHOICES)
    cast_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('request', 'voter')  # one vote per signatory per request

    def __str__(self):
        return f"{self.voter.phone_number} voted {self.vote} on {self.request}"


class MemberTrustScore(models.Model):
    """
    Trust score for a group member (0–100).
    Recalculated monthly by a Celery task.
    Feeds into the credit scoring engine (Module 5).

    Formula weights (roadmap spec):
      on_time_rate     40%
      tenure_months    20%
      withdrawal_behaviour  20%
      dispute_history  20%
    """
    member = models.ForeignKey(GroupMember, on_delete=models.CASCADE, related_name='trust_scores')
    score = models.IntegerField(default=50)

    # Raw input components — stored for transparency and auditability
    on_time_rate = models.FloatField(default=0.0)        # 0.0–1.0
    tenure_months = models.IntegerField(default=0)
    withdrawal_flags = models.IntegerField(default=0)    # suspicious withdrawal count
    dispute_count = models.IntegerField(default=0)

    calculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-calculated_at']
        get_latest_by = 'calculated_at'

    @classmethod
    def calculate(cls, group_member):
        """
        Compute and save a new trust score entry for the given GroupMember.
        Returns the new MemberTrustScore instance.
        """
        # On-time rate from contribution streak vs total cycles
        # (contributions module will provide this; default to 1.0 if no data yet)
        on_time_rate = group_member.contribution_streak / max(group_member.contribution_streak + 1, 1)

        # Tenure in months since joining
        if group_member.joined_at:
            delta = timezone.now() - group_member.joined_at
            tenure_months = delta.days // 30
        else:
            tenure_months = 0

        # Withdrawal flags: how many flagged requests this member initiated
        withdrawal_flags = WithdrawalRequest.objects.filter(
            requested_by=group_member.user,
            group=group_member.group,
            status=WithdrawalRequest.STATUS_FLAGGED,
        ).count()

        # Dispute count placeholder (will be wired up when disputes model exists)
        dispute_count = 0

        # Weighted score (0–100)
        score = int(
            (on_time_rate * 40)
            + (min(tenure_months / 24, 1.0) * 20)   # max tenure bonus at 24 months
            + (max(0, 1 - withdrawal_flags * 0.2) * 20)
            + (max(0, 1 - dispute_count * 0.25) * 20)
        )
        score = max(0, min(100, score))

        return cls.objects.create(
            member=group_member,
            score=score,
            on_time_rate=on_time_rate,
            tenure_months=tenure_months,
            withdrawal_flags=withdrawal_flags,
            dispute_count=dispute_count,
        )

    def __str__(self):
        return f"{self.member} — Trust Score: {self.score}"
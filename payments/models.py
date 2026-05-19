from django.conf import settings
from django.db import models
from django.db.models import F
from django.utils import timezone


class Transaction(models.Model):
    """
    Immutable record of every M-Pesa interaction (STK Push or B2C).
    Audit fields: actor phone, IP, device fingerprint, timestamp.
    """
    TYPE_CONTRIBUTION = 'CONTRIBUTION'
    TYPE_DISBURSEMENT = 'DISBURSEMENT'
    TYPE_ROTATION = 'ROTATION'
    TYPE_LOAN = 'LOAN'
    TYPE_CHOICES = [
        (TYPE_CONTRIBUTION, 'Contribution (C2B)'),
        (TYPE_DISBURSEMENT, 'Disbursement (B2C)'),
        (TYPE_ROTATION, 'Rotation Payout (B2C)'),
        (TYPE_LOAN, 'Loan Disbursement (B2C)'),
    ]

    STATUS_PENDING = 'PENDING'
    STATUS_SUCCESS = 'SUCCESS'
    STATUS_FAILED = 'FAILED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
    ]

    # Daraja checkout request ID — used to match STK callback
    checkout_request_id = models.CharField(max_length=100, unique=True, null=True, blank=True)

    # M-Pesa receipt number — populated after successful callback
    mpesa_reference = models.CharField(max_length=50, null=True, blank=True)

    phone_number = models.CharField(max_length=15)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)

    # Link to contribution (nullable — disbursements won't have one)
    contribution = models.OneToOneField(
        'contributions.Contribution',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='transaction',
    )

    # Audit fields
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device_fingerprint = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_type} {self.amount} [{self.status}] — {self.phone_number}"


class GroupTreasury(models.Model):
    """
    Single source of truth for a group's funds.
    All balance mutations go through credit() and debit() to use
    atomic F() expressions — no race conditions.
    """
    group = models.OneToOneField(
        'groups.Group', on_delete=models.CASCADE, related_name='treasury'
    )
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # Configurable daily disbursement ceiling (KES)
    daily_disbursement_limit = models.DecimalField(max_digits=12, decimal_places=2, default=50000)
    updated_at = models.DateTimeField(auto_now=True)

    def credit(self, amount):
        """Atomically add funds."""
        GroupTreasury.objects.filter(pk=self.pk).update(balance=F('balance') + amount)
        self.refresh_from_db()

    def debit(self, amount):
        """Atomically subtract funds. Raises ValueError if insufficient."""
        if self.balance < amount:
            raise ValueError(f"Insufficient treasury balance. Available: {self.balance}, Requested: {amount}")
        GroupTreasury.objects.filter(pk=self.pk).update(balance=F('balance') - amount)
        self.refresh_from_db()

    def today_disbursed(self):
        """Sum of successful B2C disbursements today — used for daily limit check."""
        from django.db.models import Sum
        today = timezone.now().date()
        total = (
            Disbursement.objects.filter(
                treasury=self,
                status=Disbursement.STATUS_SUCCESS,
                created_at__date=today,
            ).aggregate(Sum('amount'))['amount__sum']
        )
        return total or 0

    def __str__(self):
        return f"{self.group.name} Treasury — KES {self.balance}"


class TreasuryLedgerEntry(models.Model):
    """
    Double-entry style ledger — every treasury movement is recorded here.
    Types: contribution, disbursement, fee, interest.
    """
    TYPE_CONTRIBUTION = 'CONTRIBUTION'
    TYPE_DISBURSEMENT = 'DISBURSEMENT'
    TYPE_FEE = 'FEE'
    TYPE_INTEREST = 'INTEREST'
    TYPE_CHOICES = [
        (TYPE_CONTRIBUTION, 'Contribution'),
        (TYPE_DISBURSEMENT, 'Disbursement'),
        (TYPE_FEE, 'Fee'),
        (TYPE_INTEREST, 'Interest'),
    ]

    treasury = models.ForeignKey(GroupTreasury, on_delete=models.PROTECT, related_name='ledger_entries')
    entry_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)
    reference = models.CharField(max_length=100, blank=True)   # M-Pesa receipt or internal ref
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.entry_type} KES {self.amount} — {self.description}"


class Disbursement(models.Model):
    """
    B2C payout record. Always created before calling Daraja — status starts PENDING.
    Linked to the withdrawal request that authorised it.
    Fraud check: same phone cannot receive >3 disbursements in 24 hours.
    """
    TYPE_ROTATION = 'ROTATION'
    TYPE_WITHDRAWAL = 'WITHDRAWAL'
    TYPE_LOAN = 'LOAN'
    TYPE_CHOICES = [
        (TYPE_ROTATION, 'Rotation Payout'),
        (TYPE_WITHDRAWAL, 'Withdrawal'),
        (TYPE_LOAN, 'Loan Disbursement'),
    ]

    STATUS_PENDING = 'PENDING'
    STATUS_SUCCESS = 'SUCCESS'
    STATUS_FAILED = 'FAILED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
    ]

    treasury = models.ForeignKey(GroupTreasury, on_delete=models.PROTECT, related_name='disbursements')
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='disbursements_received'
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    disbursement_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)

    # Daraja conversation/originator ID for B2C tracking
    conversation_id = models.CharField(max_length=100, blank=True)
    mpesa_reference = models.CharField(max_length=50, blank=True)

    # Linked to the authorising withdrawal request (optional — rotation has no explicit request)
    withdrawal_request = models.OneToOneField(
        'groups.WithdrawalRequest',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='disbursement',
    )

    retry_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Audit
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device_fingerprint = models.CharField(max_length=255, blank=True)

    @classmethod
    def fraud_check(cls, phone_number) -> bool:
        """
        Returns True if this phone has received >= 3 disbursements in the last 24 hours.
        Caller should reject the disbursement if True.
        """
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(hours=24)
        count = cls.objects.filter(
            recipient__phone_number=phone_number,
            status=cls.STATUS_SUCCESS,
            created_at__gte=cutoff,
        ).count()
        return count >= 3

    def __str__(self):
        return f"{self.disbursement_type} KES {self.amount} → {self.recipient.phone_number} [{self.status}]"
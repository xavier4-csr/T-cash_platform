import random
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


class CustomUserManager(BaseUserManager):
    def create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError('The Phone Number field must be set')
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(phone_number, password, **extra_fields)


# E.164 format validator: +254XXXXXXXXX
phone_regex = RegexValidator(
    regex=r'^\+254\d{9}$',
    message="Phone number must be in E.164 format: +254XXXXXXXXX"
)


class User(AbstractUser):
    """
    Custom User model using phone_number as the primary identifier.
    Supports KYC tier system and PIN-based payment confirmations.
    """
    username = None  # Remove username field entirely

    phone_number = models.CharField(
        max_length=15,
        unique=True,
        validators=[phone_regex]
    )

    # KYC Tier system (roadmap spec)
    # Tier 0 = phone only
    # Tier 1 = name + ID number provided
    # Tier 2 = ID verified by admin
    KYC_TIER_0 = 0
    KYC_TIER_1 = 1
    KYC_TIER_2 = 2
    KYC_TIER_CHOICES = [
        (KYC_TIER_0, 'Phone Only'),
        (KYC_TIER_1, 'Name + ID Provided'),
        (KYC_TIER_2, 'ID Verified'),
    ]
    kyc_tier = models.IntegerField(default=KYC_TIER_0, choices=KYC_TIER_CHOICES)

    # Optional KYC fields — enforced only when transaction limits are reached
    id_number = models.CharField(max_length=20, blank=True, null=True)
    profile_photo = models.ImageField(upload_to='profiles/', blank=True, null=True)

    # 4-digit PIN for in-app payment confirmations — stored hashed (bcrypt via make_password)
    pin = models.CharField(max_length=128, blank=True)

    # OTP brute-force protection
    otp_failure_count = models.IntegerField(default=0)
    otp_locked_until = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def set_pin(self, raw_pin):
        """Hash and store the 4-digit PIN."""
        self.pin = make_password(raw_pin)
        self.save(update_fields=['pin'])

    def is_otp_locked(self):
        """Return True if the account is temporarily locked from OTP attempts."""
        if self.otp_locked_until and timezone.now() < self.otp_locked_until:
            return True
        return False

    def record_otp_failure(self):
        """
        Increment failure counter. Lock account for 30 minutes after 5 failures.
        Roadmap spec: max 5 wrong attempts → lock for 30 minutes.
        """
        self.otp_failure_count += 1
        if self.otp_failure_count >= 5:
            self.otp_locked_until = timezone.now() + timedelta(minutes=30)
            self.otp_failure_count = 0  # Reset counter after locking
        self.save(update_fields=['otp_failure_count', 'otp_locked_until'])

    def reset_otp_failures(self):
        """Clear failure counter on successful OTP verification."""
        self.otp_failure_count = 0
        self.otp_locked_until = None
        self.save(update_fields=['otp_failure_count', 'otp_locked_until'])

    def __str__(self):
        return self.phone_number


class OTPCode(models.Model):
    """
    One-time password codes for phone number verification.
    10-minute expiry. Max 3 requests per phone per 10 minutes.
    """
    phone_number = models.CharField(max_length=15)
    code = models.CharField(max_length=6)  # Fixed: was Charfield (typo)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=10)
        super().save(*args, **kwargs)

    def is_valid(self):
        """Return True if code has not been used and has not expired."""
        return not self.is_used and timezone.now() < self.expires_at

    @classmethod
    def recent_request_count(cls, phone_number):
        """
        Count OTP requests for this phone in the last 10 minutes.
        Used to enforce the 3-request-per-10-minutes rate limit.
        """
        window_start = timezone.now() - timedelta(minutes=10)
        return cls.objects.filter(
            phone_number=phone_number,
            created_at__gte=window_start
        ).count()

    def __str__(self):
        return f"{self.phone_number} - {self.code}"
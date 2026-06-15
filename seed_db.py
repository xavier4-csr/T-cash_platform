import os
import django
from django.utils import timezone
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from users.models import User
from groups.models import Group, GroupMember
from contributions.models import ContributionCycle, Contribution
from notifications.models import Notification

def seed():
    phone = '+254700000000'
    user, created = User.objects.get_or_create(phone_number=phone)
    if created:
        user.set_password('superuser123')
        user.is_superuser = True
        user.is_staff = True
        user.save()

    # Create a group
    group, _ = Group.objects.get_or_create(
        name="Mama Mboga Collective",
        defaults={
            "description": "Weekly vendors' chama, Gikomba market",
            "group_type": "ROTATING",
            "contribution_amount": 500.00,
            "frequency": "WEEKLY",
            "max_members": 25,
            "created_by": user
        }
    )

    membership, _ = GroupMember.objects.get_or_create(
        group=group,
        user=user,
        defaults={
            "role": "ADMIN",
            "status": "ACTIVE",
            "joined_at": timezone.now()
        }
    )

    # Create a cycle
    cycle, _ = ContributionCycle.objects.get_or_create(
        group=group,
        cycle_number=1,
        defaults={
            "due_date": timezone.now().date() + timedelta(days=7),
        }
    )

    # Create a contribution
    Contribution.objects.get_or_create(
        cycle=cycle,
        member=membership,
        defaults={
            "amount": group.contribution_amount,
            "status": "PAID"
        }
    )

    # Create a notification
    Notification.objects.get_or_create(
        recipient=user,
        title="Contribution recorded successfully",
        defaults={
            "body": "KES 500 to Mama Mboga Collective",
            "notification_type": "SYSTEM",
            "metadata": {}
        }
    )

    print("Database seeded with mock data for", phone)

if __name__ == '__main__':
    seed()

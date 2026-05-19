from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationPreference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sms_enabled', models.BooleanField(default=True)),
                ('push_enabled', models.BooleanField(default=True)),
                ('in_app_enabled', models.BooleanField(default=True)),
                ('marketing_opted_in', models.BooleanField(default=False)),
                ('push_token', models.CharField(blank=True, max_length=255)),
                ('push_token_updated_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='notification_prefs', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notification_type', models.CharField(
                    choices=[
                        ('CONTRIBUTION_REMINDER', 'Contribution Reminder'),
                        ('CONTRIBUTION_OVERDUE', 'Contribution Overdue'),
                        ('CONTRIBUTION_CONFIRMED', 'Contribution Confirmed'),
                        ('DISBURSEMENT_RECEIVED', 'Disbursement Received'),
                        ('WITHDRAWAL_VOTE', 'Withdrawal Vote Required'),
                        ('MEMBER_JOINED', 'Member Joined'),
                        ('BADGE_AWARDED', 'Badge Awarded'),
                        ('GENERAL', 'General'),
                    ],
                    max_length=40,
                )),
                ('channel', models.CharField(
                    choices=[('IN_APP', 'In-App'), ('SMS', 'SMS'), ('PUSH', 'Push')],
                    default='IN_APP', max_length=10,
                )),
                ('title', models.CharField(max_length=100)),
                ('body', models.TextField()),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        # Remove username field (set to None in model)
        migrations.RemoveField(model_name='user', name='username'),

        # KYC tier
        migrations.AddField(
            model_name='user',
            name='kyc_tier',
            field=models.IntegerField(
                choices=[(0, 'Phone Only'), (1, 'Name + ID Provided'), (2, 'ID Verified')],
                default=0,
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='id_number',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='profile_photo',
            field=models.ImageField(blank=True, null=True, upload_to='profiles/'),
        ),

        # PIN
        migrations.AddField(
            model_name='user',
            name='pin',
            field=models.CharField(blank=True, max_length=128),
        ),

        # OTP brute-force protection
        migrations.AddField(
            model_name='user',
            name='otp_failure_count',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='user',
            name='otp_locked_until',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
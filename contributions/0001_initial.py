from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('groups', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContributionCycle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cycle_number', models.PositiveIntegerField()),
                ('due_date', models.DateField()),
                ('is_closed', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cycles', to='groups.group')),
            ],
            options={'ordering': ['cycle_number']},
        ),
        migrations.AlterUniqueTogether(
            name='contributioncycle',
            unique_together={('group', 'cycle_number')},
        ),
        migrations.CreateModel(
            name='Contribution',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('status', models.CharField(
                    choices=[('PENDING', 'Pending'), ('PAID', 'Paid'), ('LATE', 'Late'), ('MISSED', 'Missed'), ('REVERSED', 'Reversed')],
                    default='PENDING', max_length=10,
                )),
                ('mpesa_reference', models.CharField(blank=True, max_length=50, null=True, unique=True)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('cycle', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='contributions', to='contributions.contributioncycle')),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='contributions', to='groups.groupmember')),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='contribution',
            unique_together={('cycle', 'member')},
        ),
        migrations.CreateModel(
            name='ContributionReversal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reason', models.TextField()),
                ('approved_by_admin', models.BooleanField(default=False)),
                ('approved_by_treasurer', models.BooleanField(default=False)),
                ('status', models.CharField(
                    choices=[('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')],
                    default='PENDING', max_length=10,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('contribution', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='reversal', to='contributions.contribution')),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reversal_requests', to='users.user')),
            ],
        ),
        migrations.CreateModel(
            name='RotationSchedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('position', models.PositiveIntegerField()),
                ('has_received', models.BooleanField(default=False)),
                ('received_at', models.DateTimeField(blank=True, null=True)),
                ('skipped', models.BooleanField(default=False)),
                ('cycle', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rotation_slots', to='contributions.contributioncycle')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rotation_schedule', to='groups.group')),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='rotation_slots', to='groups.groupmember')),
            ],
            options={'ordering': ['position']},
        ),
        migrations.AlterUniqueTogether(
            name='rotationschedule',
            unique_together={('group', 'cycle', 'position')},
        ),
        migrations.CreateModel(
            name='Badge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('badge_type', models.CharField(
                    choices=[('STREAK_3', '3-Month Streak 🔥'), ('STREAK_6', '6-Month Streak ⭐'), ('STREAK_12', '12-Month Streak 🏆')],
                    max_length=20,
                )),
                ('awarded_at', models.DateTimeField(auto_now_add=True)),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='badges', to='groups.groupmember')),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='badge',
            unique_together={('member', 'badge_type')},
        ),
    ]
from rest_framework import serializers
from .models import Badge, Contribution, ContributionCycle, ContributionReversal, RotationSchedule


class ContributionCycleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContributionCycle
        fields = ['id', 'group', 'cycle_number', 'due_date', 'is_closed', 'created_at']
        read_only_fields = ['id', 'created_at']


class ContributionSerializer(serializers.ModelSerializer):
    member_phone = serializers.CharField(source='member.user.phone_number', read_only=True)
    cycle_number = serializers.IntegerField(source='cycle.cycle_number', read_only=True)
    due_date = serializers.DateField(source='cycle.due_date', read_only=True)

    class Meta:
        model = Contribution
        fields = [
            'id', 'cycle', 'cycle_number', 'due_date',
            'member', 'member_phone', 'amount', 'status',
            'mpesa_reference', 'paid_at', 'created_at',
        ]
        read_only_fields = [
            'id', 'cycle_number', 'due_date', 'member_phone',
            'status', 'mpesa_reference', 'paid_at', 'created_at',
        ]


class ContributionReversalSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContributionReversal
        fields = [
            'id', 'contribution', 'reason', 'requested_by',
            'approved_by_admin', 'approved_by_treasurer',
            'status', 'created_at', 'resolved_at',
        ]
        read_only_fields = [
            'id', 'requested_by', 'approved_by_admin',
            'approved_by_treasurer', 'status', 'created_at', 'resolved_at',
        ]


class RotationScheduleSerializer(serializers.ModelSerializer):
    member_phone = serializers.CharField(source='member.user.phone_number', read_only=True)

    class Meta:
        model = RotationSchedule
        fields = ['id', 'position', 'member', 'member_phone', 'has_received', 'received_at', 'skipped']
        read_only_fields = ['id', 'member_phone', 'has_received', 'received_at']


class BadgeSerializer(serializers.ModelSerializer):
    badge_label = serializers.CharField(source='get_badge_type_display', read_only=True)

    class Meta:
        model = Badge
        fields = ['id', 'badge_type', 'badge_label', 'awarded_at']
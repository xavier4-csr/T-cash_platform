from rest_framework import serializers
from .models import Group, GroupMember, WithdrawalRequest, WithdrawalVote, MemberTrustScore


class GroupSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()
    is_full = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = [
            'id', 'name', 'description', 'group_type', 'group_code',
            'status', 'contribution_amount', 'frequency',
            'max_members', 'withdrawal_quorum',
            'member_count', 'is_full', 'created_at',
        ]
        read_only_fields = ['id', 'group_code', 'status', 'created_at', 'member_count', 'is_full']

    def get_member_count(self, obj):
        return obj.member_count()

    def get_is_full(self, obj):
        return obj.is_full()


class GroupMemberSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(source='user.phone_number', read_only=True)
    trust_score = serializers.SerializerMethodField()

    class Meta:
        model = GroupMember
        fields = ['id', 'phone_number', 'role', 'status', 'joined_at', 'contribution_streak', 'trust_score']
        read_only_fields = ['id', 'phone_number', 'joined_at', 'contribution_streak', 'trust_score']

    def get_trust_score(self, obj):
        latest = obj.trust_scores.order_by('-calculated_at').first()
        return latest.score if latest else None


class WithdrawalRequestSerializer(serializers.ModelSerializer):
    requested_by_phone = serializers.CharField(source='requested_by.phone_number', read_only=True)
    approve_count = serializers.SerializerMethodField()

    class Meta:
        model = WithdrawalRequest
        fields = [
            'id', 'group', 'requested_by_phone', 'amount', 'reason',
            'status', 'approve_count', 'created_at', 'resolved_at',
        ]
        read_only_fields = ['id', 'group', 'requested_by_phone', 'status', 'approve_count', 'created_at', 'resolved_at']

    def get_approve_count(self, obj):
        return obj.approve_count()


class WithdrawalVoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = WithdrawalVote
        fields = ['vote']
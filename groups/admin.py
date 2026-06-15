from django.contrib import admin
from .models import Group, GroupMember, GroupAuditLog, WithdrawalRequest, WithdrawalVote, MemberTrustScore


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'group_code', 'group_type', 'status', 'contribution_amount', 'frequency', 'created_at']
    list_filter = ['status', 'group_type', 'frequency']
    search_fields = ['name', 'group_code']
    readonly_fields = ['group_code', 'created_at', 'updated_at']


@admin.register(GroupMember)
class GroupMemberAdmin(admin.ModelAdmin):
    list_display = ['user', 'group', 'role', 'status', 'contribution_streak', 'joined_at']
    list_filter = ['role', 'status']
    search_fields = ['user__phone_number', 'group__name']


@admin.register(GroupAuditLog)
class GroupAuditLogAdmin(admin.ModelAdmin):
    list_display = ['group', 'actor', 'action', 'timestamp']
    list_filter = ['action']
    readonly_fields = ['group', 'actor', 'action', 'detail', 'timestamp']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ['group', 'requested_by', 'amount', 'status', 'created_at']
    list_filter = ['status']
    readonly_fields = ['created_at', 'resolved_at']


@admin.register(WithdrawalVote)
class WithdrawalVoteAdmin(admin.ModelAdmin):
    list_display = ['request', 'voter', 'vote', 'cast_at']
    readonly_fields = ['cast_at']


@admin.register(MemberTrustScore)
class MemberTrustScoreAdmin(admin.ModelAdmin):
    list_display = ['member', 'score', 'on_time_rate', 'tenure_months', 'calculated_at']
    readonly_fields = ['calculated_at']

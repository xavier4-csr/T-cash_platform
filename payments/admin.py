from django.contrib import admin
from .models import Badge, Contribution, ContributionCycle, ContributionReversal, RotationSchedule


@admin.register(ContributionCycle)
class ContributionCycleAdmin(admin.ModelAdmin):
    list_display = ['group', 'cycle_number', 'due_date', 'is_closed', 'created_at']
    list_filter = ['is_closed']
    search_fields = ['group__name']


@admin.register(Contribution)
class ContributionAdmin(admin.ModelAdmin):
    list_display = ['member', 'cycle', 'amount', 'status', 'mpesa_reference', 'paid_at']
    list_filter = ['status']
    search_fields = ['member__user__phone_number', 'mpesa_reference']
    readonly_fields = ['mpesa_reference', 'paid_at', 'created_at']

    def has_change_permission(self, request, obj=None):
        # Contributions are immutable — no editing in admin
        return False


@admin.register(ContributionReversal)
class ContributionReversalAdmin(admin.ModelAdmin):
    list_display = ['contribution', 'requested_by', 'status', 'approved_by_admin', 'approved_by_treasurer', 'created_at']
    list_filter = ['status']


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ['member', 'badge_type', 'awarded_at']
    list_filter = ['badge_type']


admin.site.register(RotationSchedule)
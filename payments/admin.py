from django.contrib import admin
from .models import Transaction, GroupTreasury, TreasuryLedgerEntry, Disbursement


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['phone_number', 'amount', 'transaction_type', 'status', 'created_at']
    list_filter = ['transaction_type', 'status']
    search_fields = ['phone_number', 'checkout_request_id', 'mpesa_reference']
    readonly_fields = ['created_at']


@admin.register(GroupTreasury)
class GroupTreasuryAdmin(admin.ModelAdmin):
    list_display = ['group', 'balance', 'daily_disbursement_limit', 'updated_at']
    search_fields = ['group__name']
    readonly_fields = ['updated_at']


@admin.register(TreasuryLedgerEntry)
class TreasuryLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ['treasury', 'entry_type', 'amount', 'description', 'created_at']
    list_filter = ['entry_type']
    search_fields = ['treasury__group__name', 'reference']
    readonly_fields = ['created_at']


@admin.register(Disbursement)
class DisbursementAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'treasury', 'amount', 'disbursement_type', 'status', 'created_at']
    list_filter = ['disbursement_type', 'status']
    search_fields = ['recipient__phone_number', 'conversation_id', 'mpesa_reference']
    readonly_fields = ['created_at', 'completed_at']
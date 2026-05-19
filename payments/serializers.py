from rest_framework import serializers
from .models import Disbursement, GroupTreasury, TreasuryLedgerEntry, Transaction


class GroupTreasurySerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source='group.name', read_only=True)

    class Meta:
        model = GroupTreasury
        fields = ['id', 'group_name', 'balance', 'daily_disbursement_limit', 'updated_at']
        read_only_fields = ['id', 'balance', 'updated_at']


class TreasuryLedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = TreasuryLedgerEntry
        fields = ['id', 'entry_type', 'amount', 'description', 'reference', 'created_at']


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            'id', 'phone_number', 'amount', 'transaction_type',
            'status', 'mpesa_reference', 'created_at',
        ]


class DisbursementSerializer(serializers.ModelSerializer):
    recipient_phone = serializers.CharField(source='recipient.phone_number', read_only=True)

    class Meta:
        model = Disbursement
        fields = [
            'id', 'recipient_phone', 'amount', 'disbursement_type',
            'status', 'mpesa_reference', 'retry_count', 'created_at', 'completed_at',
        ]
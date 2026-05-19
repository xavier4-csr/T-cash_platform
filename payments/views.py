import hashlib
import hmac
import logging

from django.conf import settings
from django.db import transaction as db_transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from groups.models import Group, GroupMember, WithdrawalRequest
from .models import Disbursement, GroupTreasury, TreasuryLedgerEntry, Transaction
from .serializers import (
    DisbursementSerializer,
    GroupTreasurySerializer,
    TreasuryLedgerEntrySerializer,
    TransactionSerializer,
)
from .tasks import handle_b2c_result, process_disbursement

logger = logging.getLogger(__name__)


def _get_membership(user, group):
    return GroupMember.objects.filter(
        user=user, group=group, status=GroupMember.STATUS_ACTIVE
    ).first()


# ---------------------------------------------------------------------------
# Group Treasury — balance & ledger
# ---------------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def treasury_detail(request, group_id):
    """
    Return treasury balance and recent ledger entries.
    Any active member can view. Full ledger paginated.
    """
    group = get_object_or_404(Group, id=group_id)
    if not _get_membership(request.user, group):
        return Response({'error': 'Not a member of this group.'}, status=status.HTTP_403_FORBIDDEN)

    treasury, _ = GroupTreasury.objects.get_or_create(group=group)
    ledger = treasury.ledger_entries.all()[:50]   # most recent 50

    return Response({
        'treasury': GroupTreasurySerializer(treasury).data,
        'ledger': TreasuryLedgerEntrySerializer(ledger, many=True).data,
    })


# ---------------------------------------------------------------------------
# Trigger Disbursement after withdrawal approval
# Called internally when WithdrawalRequest reaches APPROVED status
# ---------------------------------------------------------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_disbursement(request, group_id, withdrawal_request_id):
    """
    Admin triggers the disbursement after a WithdrawalRequest is APPROVED.
    Validates:
     - Request is APPROVED (multi-sig passed)
     - Treasury has sufficient balance
     - Daily disbursement limit not exceeded
     - Fraud check (recipient hasn't received >3 in 24h)

    The actual B2C call is offloaded to Celery (never done synchronously).
    """
    group = get_object_or_404(Group, id=group_id)
    membership = _get_membership(request.user, group)

    if not membership or membership.role != GroupMember.ROLE_ADMIN:
        return Response({'error': 'Only the group admin can trigger disbursements.'}, status=status.HTTP_403_FORBIDDEN)

    wr = get_object_or_404(WithdrawalRequest, id=withdrawal_request_id, group=group)

    if wr.status != WithdrawalRequest.STATUS_APPROVED:
        return Response(
            {'error': f'Withdrawal request is not APPROVED (current status: {wr.status}).'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Prevent double-triggering
    if hasattr(wr, 'disbursement') and wr.disbursement.status in [
        Disbursement.STATUS_PENDING, Disbursement.STATUS_SUCCESS
    ]:
        return Response({'error': 'A disbursement for this request is already in progress or completed.'}, status=status.HTTP_400_BAD_REQUEST)

    treasury, _ = GroupTreasury.objects.get_or_create(group=group)

    # Balance check
    if treasury.balance < wr.amount:
        return Response({'error': f'Insufficient treasury balance. Available: KES {treasury.balance}.'}, status=status.HTTP_400_BAD_REQUEST)

    # Daily limit check
    today_disbursed = treasury.today_disbursed()
    if today_disbursed + wr.amount > treasury.daily_disbursement_limit:
        return Response(
            {'error': f'Daily disbursement limit (KES {treasury.daily_disbursement_limit}) would be exceeded. Manual admin approval required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Fraud check on recipient
    if Disbursement.fraud_check(wr.requested_by.phone_number):
        return Response(
            {'error': 'Fraud flag: this recipient has received too many disbursements in the last 24 hours.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    with db_transaction.atomic():
        # Debit treasury immediately to reserve funds
        treasury.debit(wr.amount)

        disbursement = Disbursement.objects.create(
            treasury=treasury,
            recipient=wr.requested_by,
            amount=wr.amount,
            disbursement_type=Disbursement.TYPE_WITHDRAWAL,
            withdrawal_request=wr,
            ip_address=request.META.get('REMOTE_ADDR'),
        )

        wr.status = WithdrawalRequest.STATUS_DISBURSED
        wr.resolved_at = timezone.now()
        wr.save(update_fields=['status', 'resolved_at'])

    # Offload to Celery — never block the request thread
    process_disbursement.delay(disbursement.id)

    return Response(
        {'message': 'Disbursement queued. Funds will be sent to the recipient\'s M-Pesa shortly.'},
        status=status.HTTP_202_ACCEPTED,
    )


# ---------------------------------------------------------------------------
# B2C Result Callback — Safaricom calls this after B2C completes
# ---------------------------------------------------------------------------
@csrf_exempt
@api_view(['POST'])
def b2c_result_callback(request):
    """
    Safaricom posts the B2C result here.
    Signature validated then offloaded to Celery for DB update.
    """
    expected_sig = hmac.new(
        settings.MPESA_CALLBACK_SECRET.encode(),
        request.body,
        hashlib.sha256,
    ).hexdigest()
    received_sig = request.headers.get('X-Mpesa-Signature', '')

    if not hmac.compare_digest(expected_sig, received_sig):
        logger.warning("B2C callback: invalid signature.")
        return Response({'ResultCode': 1, 'ResultDesc': 'Invalid signature'})

    handle_b2c_result.delay(request.data)
    return Response({'ResultCode': 0, 'ResultDesc': 'Accepted'})


@csrf_exempt
@api_view(['POST'])
def b2c_timeout_callback(request):
    """Safaricom timeout callback — log and return 200 so they don't retry indefinitely."""
    logger.warning("B2C timeout received: %s", request.data)
    return Response({'ResultCode': 0, 'ResultDesc': 'Accepted'})


# ---------------------------------------------------------------------------
# Transaction history
# ---------------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_transactions(request):
    """Return the authenticated user's transaction history."""
    txns = Transaction.objects.filter(phone_number=request.user.phone_number).order_by('-created_at')[:100]
    return Response(TransactionSerializer(txns, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def group_disbursements(request, group_id):
    """List all disbursements for a group (admin/treasurer only)."""
    group = get_object_or_404(Group, id=group_id)
    membership = _get_membership(request.user, group)

    if not membership or membership.role not in [GroupMember.ROLE_ADMIN, GroupMember.ROLE_TREASURER]:
        return Response({'error': 'Admin or treasurer access required.'}, status=status.HTTP_403_FORBIDDEN)

    treasury = get_object_or_404(GroupTreasury, group=group)
    disbursements = treasury.disbursements.select_related('recipient').order_by('-created_at')
    return Response(DisbursementSerializer(disbursements, many=True).data)
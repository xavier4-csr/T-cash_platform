"""
Contributions views — STK Push initiation and M-Pesa callback webhook.

Flow:
  1. Member calls POST /api/contributions/<group_id>/pay/ → STK Push sent
  2. Safaricom hits POST /api/contributions/stk/callback/ with result
  3. Callback creates/updates Contribution record and credits treasury
"""
import hashlib
import hmac
import logging

from django.conf import settings
from django.db import transaction as db_transaction
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from groups.models import Group, GroupMember
from payments.models import GroupTreasury, TreasuryLedgerEntry, Transaction
from payments.mpesa import trigger_stk_push

from .models import Contribution, ContributionCycle, Badge
from .serializers import ContributionSerializer, ContributionCycleSerializer, BadgeSerializer

logger = logging.getLogger(__name__)


def _get_active_membership(user, group):
    return GroupMember.objects.filter(
        user=user, group=group, status=GroupMember.STATUS_ACTIVE
    ).first()


# ---------------------------------------------------------------------------
# Contribution Cycles — admin creates cycles, members view them
# ---------------------------------------------------------------------------
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def cycle_list_create(request, group_id):
    """
    GET  → list all cycles for the group (active members only).
    POST → create a new cycle (admin only).
    """
    group = get_object_or_404(Group, id=group_id)
    membership = _get_active_membership(request.user, group)

    if not membership:
        return Response({'error': 'Not a member of this group.'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        cycles = ContributionCycle.objects.filter(group=group).order_by('cycle_number')
        return Response(ContributionCycleSerializer(cycles, many=True).data)

    # POST — admin only
    if membership.role != GroupMember.ROLE_ADMIN:
        return Response({'error': 'Only the group admin can create cycles.'}, status=status.HTTP_403_FORBIDDEN)

    serializer = ContributionCycleSerializer(data={**request.data, 'group': group.id})
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    cycle = serializer.save(group=group)

    # Pre-create Contribution records for each active member
    active_members = group.memberships.filter(status=GroupMember.STATUS_ACTIVE)
    contributions = [
        Contribution(cycle=cycle, member=m, amount=group.contribution_amount)
        for m in active_members
    ]
    Contribution.objects.bulk_create(contributions, ignore_conflicts=True)

    return Response(ContributionCycleSerializer(cycle).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Initiate contribution payment via STK Push
# ---------------------------------------------------------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_contribution(request, group_id):
    """
    Trigger an STK Push for the current cycle's contribution.
    Creates a Transaction record (PENDING) and returns immediately.
    The actual credit happens in the M-Pesa callback.
    """
    group = get_object_or_404(Group, id=group_id)
    membership = _get_active_membership(request.user, group)

    if not membership:
        return Response({'error': 'Not a member of this group.'}, status=status.HTTP_403_FORBIDDEN)

    cycle_id = request.data.get('cycle_id')
    if not cycle_id:
        return Response({'error': 'cycle_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

    cycle = get_object_or_404(ContributionCycle, id=cycle_id, group=group)

    if cycle.is_closed:
        return Response({'error': 'This cycle is already closed.'}, status=status.HTTP_400_BAD_REQUEST)

    # Find or create the contribution record for this member/cycle
    contribution, _ = Contribution.objects.get_or_create(
        cycle=cycle,
        member=membership,
        defaults={'amount': group.contribution_amount},
    )

    if contribution.status in [Contribution.STATUS_PAID, Contribution.STATUS_LATE]:
        return Response({'error': 'You have already paid for this cycle.'}, status=status.HTTP_400_BAD_REQUEST)

    # Create a pending transaction
    txn = Transaction.objects.create(
        phone_number=request.user.phone_number,
        amount=group.contribution_amount,
        transaction_type=Transaction.TYPE_CONTRIBUTION,
        ip_address=request.META.get('REMOTE_ADDR'),
        contribution=contribution,
    )

    success, result = trigger_stk_push(
        phone=request.user.phone_number,
        amount=int(group.contribution_amount),
        account_ref=group.group_code,
        description=f"T-Cash contribution — {group.name} Cycle {cycle.cycle_number}",
    )

    if success:
        txn.checkout_request_id = result.get('CheckoutRequestID', '')
        txn.save(update_fields=['checkout_request_id'])
        return Response({
            'message': 'STK Push sent. Check your phone to complete payment.',
            'checkout_request_id': txn.checkout_request_id,
        }, status=status.HTTP_202_ACCEPTED)
    else:
        txn.status = Transaction.STATUS_FAILED
        txn.save(update_fields=['status'])
        logger.warning("STK Push failed for %s: %s", request.user.phone_number, result)
        return Response({'error': 'STK Push failed. Please try again.', 'detail': result},
                        status=status.HTTP_502_BAD_GATEWAY)


# ---------------------------------------------------------------------------
# M-Pesa STK Push Callback — Safaricom posts here
# ---------------------------------------------------------------------------
@csrf_exempt
@api_view(['POST'])
def stk_callback(request):
    """
    Safaricom posts the STK Push result here.
    Signature validated, then Contribution marked paid and treasury credited.
    """
    # Validate HMAC signature
    expected_sig = hmac.new(
        settings.MPESA_CALLBACK_SECRET.encode(),
        request.body,
        hashlib.sha256,
    ).hexdigest()
    received_sig = request.headers.get('X-Mpesa-Signature', '')

    if not hmac.compare_digest(expected_sig, received_sig):
        logger.warning("STK callback: invalid signature.")
        return Response({'ResultCode': 1, 'ResultDesc': 'Invalid signature'})

    try:
        callback = request.data['Body']['stkCallback']
        checkout_request_id = callback['CheckoutRequestID']
        result_code = callback['ResultCode']

        txn = Transaction.objects.select_related('contribution__cycle__group').get(
            checkout_request_id=checkout_request_id
        )

        if result_code == 0:
            # Payment succeeded
            items = {
                i['Name']: i['Value']
                for i in callback.get('CallbackMetadata', {}).get('Item', [])
            }
            mpesa_ref = items.get('MpesaReceiptNumber', '')

            with db_transaction.atomic():
                txn.status = Transaction.STATUS_SUCCESS
                txn.mpesa_reference = mpesa_ref
                txn.save(update_fields=['status', 'mpesa_reference'])

                if txn.contribution:
                    contribution = txn.contribution
                    contribution.mark_paid(mpesa_ref)

                    # Credit group treasury
                    treasury, _ = GroupTreasury.objects.get_or_create(
                        group=contribution.cycle.group
                    )
                    treasury.credit(contribution.amount)

                    TreasuryLedgerEntry.objects.create(
                        treasury=treasury,
                        entry_type=TreasuryLedgerEntry.TYPE_CONTRIBUTION,
                        amount=contribution.amount,
                        description=f"Contribution from {txn.phone_number} — Cycle {contribution.cycle.cycle_number}",
                        reference=mpesa_ref,
                    )

                    # Fire async notification (non-blocking)
                    try:
                        from notifications.tasks import notify_contribution_confirmed
                        notify_contribution_confirmed.delay(contribution.id)
                    except Exception:
                        pass

        else:
            txn.status = Transaction.STATUS_FAILED
            txn.save(update_fields=['status'])

    except (KeyError, Transaction.DoesNotExist) as exc:
        logger.exception("STK callback processing failed: %s", exc)

    return Response({'ResultCode': 0, 'ResultDesc': 'Accepted'})


# ---------------------------------------------------------------------------
# Contribution History
# ---------------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def contribution_history(request, group_id):
    """List all contributions for a group cycle (members only)."""
    group = get_object_or_404(Group, id=group_id)
    membership = _get_active_membership(request.user, group)

    if not membership:
        return Response({'error': 'Not a member of this group.'}, status=status.HTTP_403_FORBIDDEN)

    cycle_id = request.query_params.get('cycle_id')
    qs = Contribution.objects.filter(cycle__group=group).select_related('member__user', 'cycle')

    if cycle_id:
        qs = qs.filter(cycle_id=cycle_id)

    return Response(ContributionSerializer(qs.order_by('-created_at'), many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_contributions(request, group_id):
    """Return the authenticated user's own contributions in this group."""
    group = get_object_or_404(Group, id=group_id)
    membership = _get_active_membership(request.user, group)

    if not membership:
        return Response({'error': 'Not a member of this group.'}, status=status.HTTP_403_FORBIDDEN)

    qs = Contribution.objects.filter(member=membership).select_related('cycle')
    return Response(ContributionSerializer(qs.order_by('-created_at'), many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_badges(request, group_id):
    """Return the authenticated user's gamification badges in this group."""
    group = get_object_or_404(Group, id=group_id)
    membership = _get_active_membership(request.user, group)

    if not membership:
        return Response({'error': 'Not a member of this group.'}, status=status.HTTP_403_FORBIDDEN)

    badges = Badge.objects.filter(member=membership).order_by('-awarded_at')
    return Response(BadgeSerializer(badges, many=True).data)
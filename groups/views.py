from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Group, GroupAuditLog, GroupMember, WithdrawalRequest, WithdrawalVote
from .serializers import (
    GroupMemberSerializer,
    GroupSerializer,
    WithdrawalRequestSerializer,
    WithdrawalVoteSerializer,
)


def get_active_membership(user, group):
    return GroupMember.objects.filter(user=user, group=group, status=GroupMember.STATUS_ACTIVE).first()


def log(group, actor, action, detail=None):
    GroupAuditLog.objects.create(group=group, actor=actor, action=action, detail=detail or {})


# ---------------------------------------------------------------------------
# Groups — Create & List
# ---------------------------------------------------------------------------
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def group_list_create(request):
    if request.method == 'GET':
        memberships = GroupMember.objects.filter(
            user=request.user, status=GroupMember.STATUS_ACTIVE
        ).select_related('group')
        groups = [m.group for m in memberships]
        return Response(GroupSerializer(groups, many=True).data)

    serializer = GroupSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    group = serializer.save(created_by=request.user)
    GroupMember.objects.create(
        group=group, user=request.user,
        role=GroupMember.ROLE_ADMIN,
        status=GroupMember.STATUS_ACTIVE,
        joined_at=timezone.now(),
    )
    log(group, request.user, 'GROUP_CREATED', {'name': group.name})
    return Response(GroupSerializer(group).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Group — Detail & Update
# ---------------------------------------------------------------------------
@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def group_detail(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    membership = get_active_membership(request.user, group)

    if not membership:
        return Response({'error': 'You are not a member of this group.'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        return Response(GroupSerializer(group).data)

    if membership.role != GroupMember.ROLE_ADMIN:
        return Response({'error': 'Only the group admin can update group settings.'}, status=status.HTTP_403_FORBIDDEN)

    changed = {
        field: {'from': str(getattr(group, field)), 'to': str(request.data[field])}
        for field in ['contribution_amount', 'withdrawal_quorum', 'frequency', 'max_members']
        if field in request.data
    }
    serializer = GroupSerializer(group, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    serializer.save()
    if changed:
        log(group, request.user, 'RULE_CHANGED', changed)
    return Response(serializer.data)


# ---------------------------------------------------------------------------
# Join by code
# ---------------------------------------------------------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def join_group(request):
    code = request.data.get('group_code', '').upper()
    if not code:
        return Response({'error': 'group_code is required'}, status=status.HTTP_400_BAD_REQUEST)

    group = get_object_or_404(Group, group_code=code, status=Group.STATUS_ACTIVE)

    if group.is_full():
        return Response({'error': 'This group is full.'}, status=status.HTTP_400_BAD_REQUEST)

    if GroupMember.objects.filter(user=request.user, group=group).exists():
        return Response({'error': 'You have already joined or requested to join this group.'}, status=status.HTTP_400_BAD_REQUEST)

    GroupMember.objects.create(group=group, user=request.user)
    log(group, request.user, 'JOIN_REQUESTED')

    try:
        from notifications.tasks import notify_member_joined
        notify_member_joined.delay(group.id, request.user.id)
    except Exception:
        pass

    return Response({'message': f'Join request sent to {group.name}. Waiting for admin approval.'}, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def member_list(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if not get_active_membership(request.user, group):
        return Response({'error': 'Not a member of this group.'}, status=status.HTTP_403_FORBIDDEN)
    members = group.memberships.select_related('user').all()
    return Response(GroupMemberSerializer(members, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def approve_member(request, group_id, member_id):
    group = get_object_or_404(Group, id=group_id)
    admin_membership = get_active_membership(request.user, group)

    if not admin_membership or admin_membership.role != GroupMember.ROLE_ADMIN:
        return Response({'error': 'Only the group admin can approve members.'}, status=status.HTTP_403_FORBIDDEN)

    pending = get_object_or_404(GroupMember, id=member_id, group=group, status=GroupMember.STATUS_PENDING)
    action = request.data.get('action', '').upper()

    if action == 'APPROVE':
        if group.is_full():
            return Response({'error': 'Group is now full.'}, status=status.HTTP_400_BAD_REQUEST)
        pending.activate()
        if group.is_full():
            group.invalidate_code()
        log(group, request.user, 'MEMBER_APPROVED', {'user': pending.user.phone_number})
        return Response({'message': f'{pending.user.phone_number} approved.'})

    elif action == 'REJECT':
        pending.status = GroupMember.STATUS_REJECTED
        pending.save(update_fields=['status'])
        log(group, request.user, 'MEMBER_REJECTED', {'user': pending.user.phone_number})
        return Response({'message': f'{pending.user.phone_number} rejected.'})

    return Response({'error': 'action must be APPROVE or REJECT'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_member_role(request, group_id, member_id):
    group = get_object_or_404(Group, id=group_id)
    admin_membership = get_active_membership(request.user, group)

    if not admin_membership or admin_membership.role != GroupMember.ROLE_ADMIN:
        return Response({'error': 'Only the group admin can change roles.'}, status=status.HTTP_403_FORBIDDEN)

    target = get_object_or_404(GroupMember, id=member_id, group=group, status=GroupMember.STATUS_ACTIVE)
    new_role = request.data.get('role', '').upper()
    valid_roles = [GroupMember.ROLE_TREASURER, GroupMember.ROLE_SIGNATORY, GroupMember.ROLE_MEMBER]

    if new_role not in valid_roles:
        return Response({'error': f'role must be one of: {valid_roles}'}, status=status.HTTP_400_BAD_REQUEST)

    old_role = target.role
    target.role = new_role
    target.save(update_fields=['role'])
    log(group, request.user, 'ROLE_CHANGED', {'user': target.user.phone_number, 'from': old_role, 'to': new_role})
    return Response({'message': f'{target.user.phone_number} role updated to {new_role}.'})


# ---------------------------------------------------------------------------
# Withdrawal Requests
# ---------------------------------------------------------------------------
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def withdrawal_requests(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    membership = get_active_membership(request.user, group)

    if not membership:
        return Response({'error': 'Not a member of this group.'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        qs = group.withdrawal_requests.all().order_by('-created_at')
        return Response(WithdrawalRequestSerializer(qs, many=True).data)

    amount = request.data.get('amount')
    reason = request.data.get('reason', '').strip()

    if not amount or not reason:
        return Response({'error': 'amount and reason are required'}, status=status.HTTP_400_BAD_REQUEST)

    wr = WithdrawalRequest.objects.create(
        group=group, requested_by=request.user, amount=amount, reason=reason
    )
    log(group, request.user, 'WITHDRAWAL_REQUESTED', {'amount': str(amount), 'reason': reason})

    try:
        from notifications.tasks import notify_withdrawal_signatories
        notify_withdrawal_signatories.delay(wr.id)
    except Exception:
        pass

    return Response(WithdrawalRequestSerializer(wr).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cast_withdrawal_vote(request, group_id, request_id):
    group = get_object_or_404(Group, id=group_id)
    membership = get_active_membership(request.user, group)

    if not membership:
        return Response({'error': 'Not a member of this group.'}, status=status.HTTP_403_FORBIDDEN)

    if membership.role not in [GroupMember.ROLE_SIGNATORY, GroupMember.ROLE_ADMIN]:
        return Response({'error': 'Only signatories and admins can vote on withdrawal requests.'}, status=status.HTTP_403_FORBIDDEN)

    wr = get_object_or_404(WithdrawalRequest, id=request_id, group=group)

    if wr.requested_by == request.user:
        return Response({'error': 'You cannot vote on your own withdrawal request.'}, status=status.HTTP_403_FORBIDDEN)

    if wr.status != WithdrawalRequest.STATUS_PENDING:
        return Response({'error': f'This request is already {wr.status}.'}, status=status.HTTP_400_BAD_REQUEST)

    serializer = WithdrawalVoteSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if WithdrawalVote.objects.filter(request=wr, voter=request.user).exists():
        return Response({'error': 'You have already voted on this request.'}, status=status.HTTP_400_BAD_REQUEST)

    WithdrawalVote.objects.create(request=wr, voter=request.user, vote=serializer.validated_data['vote'])
    new_status = wr.check_quorum()

    log(group, request.user, 'WITHDRAWAL_VOTE_CAST', {
        'request_id': wr.id,
        'vote': serializer.validated_data['vote'],
        'new_status': new_status,
    })

    return Response({
        'message': f'Vote cast. Request status: {new_status}',
        'status': new_status,
        'approve_count': wr.approve_count(),
        'quorum_required': group.withdrawal_quorum,
    })
from django.urls import path
from .views import (
    group_list_create,
    group_detail,
    join_group,
    member_list,
    approve_member,
    update_member_role,
    withdrawal_requests,
    cast_withdrawal_vote,
)

urlpatterns = [
    # Groups — list my groups / create a new group
    path('', group_list_create, name='group-list-create'),
    # Group detail — view / update settings
    path('<int:group_id>/', group_detail, name='group-detail'),
    # Join by invite code
    path('join/', join_group, name='join-group'),

    # Members
    path('<int:group_id>/members/', member_list, name='member-list'),
    path('<int:group_id>/members/<int:member_id>/approve/', approve_member, name='approve-member'),
    path('<int:group_id>/members/<int:member_id>/role/', update_member_role, name='update-member-role'),

    # Withdrawal governance (multi-sig)
    path('<int:group_id>/withdrawals/', withdrawal_requests, name='withdrawal-requests'),
    path('<int:group_id>/withdrawals/<int:request_id>/vote/', cast_withdrawal_vote, name='cast-vote'),
]

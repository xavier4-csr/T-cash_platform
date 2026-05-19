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
    path('', group_list_create, name='group-list-create'),
    path('<int:group_id>/', group_detail, name='group-detail'),
    path('join/', join_group, name='join-group'),

    # Members
    path('<int:group_id>/members/', member_list, name='member-list'),
    path('<int:group_id>/members/<int:member_id>/approve/', approve_member, name='approve-member'),
    path('<int:group_id>/members/<int:member_id>/role/', update_member_role, name='update-member-role'),

    # Withdrawals
    path('<int:group_id>/withdrawals/', withdrawal_requests, name='withdrawal-requests'),
    path('<int:group_id>/withdrawals/<int:request_id>/vote/', cast_withdrawal_vote, name='cast-vote'),
]
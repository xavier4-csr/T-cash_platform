from django.urls import path
from .views import (
    treasury_detail,
    trigger_disbursement,
    b2c_result_callback,
    b2c_timeout_callback,
    my_transactions,
    group_disbursements,
)

urlpatterns = [
    # Transaction history for authenticated user
    path('transactions/', my_transactions, name='my-transactions'),

    # Group treasury balance + ledger
    path('groups/<int:group_id>/treasury/', treasury_detail, name='treasury-detail'),

    # Disbursement list for a group (admin/treasurer only)
    path('groups/<int:group_id>/disbursements/', group_disbursements, name='group-disbursements'),

    # Admin triggers a B2C disbursement after withdrawal is approved
    path('groups/<int:group_id>/disburse/<int:withdrawal_request_id>/', trigger_disbursement, name='trigger-disbursement'),

    # Safaricom B2C callbacks (no auth required — Safaricom calls these)
    path('b2c/result/', b2c_result_callback, name='b2c-result-callback'),
    path('b2c/timeout/', b2c_timeout_callback, name='b2c-timeout-callback'),
]

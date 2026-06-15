from django.urls import path
from .views import (
    cycle_list_create,
    initiate_contribution,
    stk_callback,
    contribution_history,
    my_contributions,
    my_badges,
)

urlpatterns = [
    # STK Push callback — no auth (Safaricom calls this)
    path('stk/callback/', stk_callback, name='stk-callback'),

    # Cycles — admin creates, members view
    path('<int:group_id>/cycles/', cycle_list_create, name='cycle-list-create'),

    # Initiate payment (STK Push) for a specific group
    path('<int:group_id>/pay/', initiate_contribution, name='initiate-contribution'),

    # Contribution history for a group
    path('<int:group_id>/history/', contribution_history, name='contribution-history'),

    # My own contributions in a group
    path('<int:group_id>/mine/', my_contributions, name='my-contributions'),

    # Gamification badges
    path('<int:group_id>/badges/', my_badges, name='my-badges'),
]

"""
Celery tasks for the payments module.

All B2C disbursements are executed here — NEVER synchronously in a request cycle.
Retry policy: up to 3 attempts with 1-hour backoff (roadmap spec).
"""
import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import Disbursement, GroupTreasury, TreasuryLedgerEntry
from .mpesa import trigger_b2c

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 3600  # 1 hour


@shared_task(bind=True, max_retries=MAX_RETRIES)
def process_disbursement(self, disbursement_id: int):
    """
    Execute a B2C disbursement via Daraja.
    Called after multi-sig quorum is reached on a WithdrawalRequest,
    or when the rotation schedule triggers a cycle payout.

    On failure: retries up to 3 times with 1-hour backoff.
    On final failure: marks disbursement FAILED and notifies admin.
    """
    try:
        disbursement = Disbursement.objects.select_related(
            'recipient', 'treasury__group'
        ).get(id=disbursement_id)
    except Disbursement.DoesNotExist:
        logger.error("Disbursement %s not found.", disbursement_id)
        return

    if disbursement.status == Disbursement.STATUS_SUCCESS:
        logger.info("Disbursement %s already succeeded — skipping.", disbursement_id)
        return

    # Fraud check
    if Disbursement.fraud_check(disbursement.recipient.phone_number):
        logger.warning(
            "Fraud flag: %s has received >=3 disbursements in 24h. Halting disbursement %s.",
            disbursement.recipient.phone_number,
            disbursement_id,
        )
        disbursement.status = Disbursement.STATUS_FAILED
        disbursement.save(update_fields=['status'])
        # TODO: trigger admin alert notification here
        return

    occasion_map = {
        Disbursement.TYPE_ROTATION: 'ROTATION',
        Disbursement.TYPE_WITHDRAWAL: 'WITHDRAWAL',
        Disbursement.TYPE_LOAN: 'LOAN',
    }
    occasion = occasion_map.get(disbursement.disbursement_type, 'PAYMENT')
    group_name = disbursement.treasury.group.name

    success, result = trigger_b2c(
        phone=disbursement.recipient.phone_number,
        amount=int(disbursement.amount),
        occasion=occasion,
        remarks=f"T-Cash {occasion} — {group_name}",
    )

    if success:
        with transaction.atomic():
            disbursement.status = Disbursement.STATUS_SUCCESS
            disbursement.conversation_id = result.get('ConversationID', '')
            disbursement.completed_at = timezone.now()
            disbursement.save(update_fields=['status', 'conversation_id', 'completed_at'])

            TreasuryLedgerEntry.objects.create(
                treasury=disbursement.treasury,
                entry_type=TreasuryLedgerEntry.TYPE_DISBURSEMENT,
                amount=disbursement.amount,
                description=f"{occasion} to {disbursement.recipient.phone_number}",
                reference=result.get('ConversationID', ''),
            )

        logger.info("Disbursement %s succeeded.", disbursement_id)

    else:
        disbursement.retry_count += 1
        disbursement.save(update_fields=['retry_count'])
        logger.warning("Disbursement %s failed (attempt %s): %s", disbursement_id, disbursement.retry_count, result)

        if disbursement.retry_count < MAX_RETRIES:
            raise self.retry(exc=Exception(str(result)), countdown=RETRY_BACKOFF_SECONDS)
        else:
            disbursement.status = Disbursement.STATUS_FAILED
            disbursement.save(update_fields=['status'])
            logger.error("Disbursement %s permanently failed after %s attempts.", disbursement_id, MAX_RETRIES)
            # TODO: trigger admin alert notification


@shared_task
def handle_b2c_result(result_data: dict):
    """
    Process the B2C result callback from Safaricom.
    Updates disbursement record with M-Pesa receipt number.
    """
    try:
        result = result_data['Result']
        conversation_id = result['ConversationID']
        result_code = result['ResultCode']

        disbursement = Disbursement.objects.get(conversation_id=conversation_id)

        if result_code == 0:
            # Extract receipt from ResultParameters
            params = {p['Key']: p['Value'] for p in result.get('ResultParameters', {}).get('ResultParameter', [])}
            disbursement.mpesa_reference = params.get('TransactionReceipt', '')
            disbursement.status = Disbursement.STATUS_SUCCESS
            disbursement.completed_at = timezone.now()
        else:
            disbursement.status = Disbursement.STATUS_FAILED

        disbursement.save(update_fields=['mpesa_reference', 'status', 'completed_at'])

    except (KeyError, Disbursement.DoesNotExist) as exc:
        logger.exception("B2C result handling failed: %s", exc)
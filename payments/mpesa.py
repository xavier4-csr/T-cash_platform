"""
Safaricom Daraja API client.
All credentials come from environment variables — never hardcoded.

Required .env keys:
  MPESA_CONSUMER_KEY
  MPESA_CONSUMER_SECRET
  MPESA_SHORTCODE
  MPESA_PASSKEY
  MPESA_B2C_SHORTCODE
  MPESA_B2C_INITIATOR_NAME
  MPESA_B2C_SECURITY_CREDENTIAL  (encrypted via Safaricom portal)
  MPESA_CALLBACK_URL             (public HTTPS URL for STK callbacks)
  MPESA_B2C_RESULT_URL           (public HTTPS URL for B2C results)
  MPESA_B2C_QUEUE_TIMEOUT_URL
  MPESA_CALLBACK_SECRET          (shared secret for signature validation)
  MPESA_ENV                      (sandbox | production)
"""

import base64
import logging
from datetime import datetime

import requests
from decouple import config

logger = logging.getLogger(__name__)

_BASE = (
    'https://sandbox.safaricom.co.ke'
    if config('MPESA_ENV', default='sandbox') == 'sandbox'
    else 'https://api.safaricom.co.ke'
)


def _get_access_token() -> str:
    """Fetch a short-lived OAuth access token from Daraja."""
    consumer_key = config('MPESA_CONSUMER_KEY')
    consumer_secret = config('MPESA_CONSUMER_SECRET')
    credentials = base64.b64encode(f"{consumer_key}:{consumer_secret}".encode()).decode()

    response = requests.get(
        f"{_BASE}/oauth/v1/generate?grant_type=client_credentials",
        headers={'Authorization': f'Basic {credentials}'},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()['access_token']


def _generate_password() -> tuple[str, str]:
    """
    Daraja STK Push password = Base64(shortcode + passkey + timestamp).
    Returns (password, timestamp).
    """
    shortcode = config('MPESA_SHORTCODE')
    passkey = config('MPESA_PASSKEY')
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    raw = f"{shortcode}{passkey}{timestamp}"
    password = base64.b64encode(raw.encode()).decode()
    return password, timestamp


def trigger_stk_push(phone: str, amount: int, account_ref: str, description: str) -> tuple[bool, dict]:
    """
    Initiate a Lipa na M-Pesa Online (STK Push) payment.

    Args:
        phone:       E.164 format +254XXXXXXXXX — converted to 254XXXXXXXXX for Daraja.
        amount:      Integer KES amount.
        account_ref: Short reference shown in member's M-Pesa message.
        description: Transaction description.

    Returns:
        (True, response_dict) on success, (False, error_dict) on failure.
    """
    try:
        token = _get_access_token()
        password, timestamp = _generate_password()

        # Daraja expects phone without leading +
        daraja_phone = phone.lstrip('+')

        payload = {
            'BusinessShortCode': config('MPESA_SHORTCODE'),
            'Password': password,
            'Timestamp': timestamp,
            'TransactionType': 'CustomerPayBillOnline',
            'Amount': amount,
            'PartyA': daraja_phone,
            'PartyB': config('MPESA_SHORTCODE'),
            'PhoneNumber': daraja_phone,
            'CallBackURL': config('MPESA_CALLBACK_URL'),
            'AccountReference': account_ref,
            'TransactionDesc': description,
        }

        response = requests.post(
            f"{_BASE}/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
            },
            timeout=15,
        )
        result = response.json()

        if result.get('ResponseCode') == '0':
            return True, result
        return False, result

    except Exception as exc:
        logger.exception("STK Push failed: %s", exc)
        return False, {'error': str(exc)}


def trigger_b2c(phone: str, amount: int, occasion: str, remarks: str) -> tuple[bool, dict]:
    """
    Business to Customer (B2C) disbursement — push funds to a member's M-Pesa.
    Always called from a Celery task, never synchronously.

    Args:
        phone:    E.164 format.
        amount:   Integer KES amount.
        occasion: Short label e.g. 'ROTATION', 'WITHDRAWAL', 'LOAN'.
        remarks:  Longer description for audit trail.

    Returns:
        (True, response_dict) on success, (False, error_dict) on failure.
    """
    try:
        token = _get_access_token()
        daraja_phone = phone.lstrip('+')

        payload = {
            'InitiatorName': config('MPESA_B2C_INITIATOR_NAME'),
            'SecurityCredential': config('MPESA_B2C_SECURITY_CREDENTIAL'),
            'CommandID': 'BusinessPayment',
            'Amount': amount,
            'PartyA': config('MPESA_B2C_SHORTCODE'),
            'PartyB': daraja_phone,
            'Remarks': remarks,
            'QueueTimeOutURL': config('MPESA_B2C_QUEUE_TIMEOUT_URL'),
            'ResultURL': config('MPESA_B2C_RESULT_URL'),
            'Occasion': occasion,
        }

        response = requests.post(
            f"{_BASE}/mpesa/b2c/v3/paymentrequest",
            json=payload,
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
            },
            timeout=15,
        )
        result = response.json()

        if result.get('ResponseCode') == '0':
            return True, result
        return False, result

    except Exception as exc:
        logger.exception("B2C disbursement failed: %s", exc)
        return False, {'error': str(exc)}
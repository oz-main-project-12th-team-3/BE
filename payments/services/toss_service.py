import base64

import requests
from django.conf import settings

TOSS_API_URL = "https://api.tosspayments.com/v1"


def _get_toss_auth_headers():
    """
    Generates the Basic Auth header for Toss Payments API.
    """
    secret_key = settings.TOSS_SECRET_KEY
    if not secret_key:
        raise ValueError("TOSS_SECRET_KEY is not set in settings.")

    # The secret key must have a colon at the end before encoding
    encoded_key = base64.b64encode(f"{secret_key}:".encode("utf-8")).decode("utf-8")
    return {
        "Authorization": f"Basic {encoded_key}",
        "Content-Type": "application/json",
    }


def create_toss_payment_request(
    order_id: str, amount: int, order_name: str, success_url: str, fail_url: str
):
    """
    Requests a payment from Toss Payments API.
    """
    url = f"{TOSS_API_URL}/payments"
    headers = _get_toss_auth_headers()

    payload = {
        "method": "카드",  # Default to card, can be expanded
        "orderId": order_id,
        "amount": amount,
        "orderName": order_name,
        "successUrl": success_url,
        "failUrl": fail_url,
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error requesting payment from Toss: {e}")
        return None


def confirm_toss_payment(payment_key: str, order_id: str, amount: int):
    """
    Confirms a payment with Toss Payments API.
    """
    url = f"{TOSS_API_URL}/payments/{payment_key}"
    headers = _get_toss_auth_headers()
    payload = {
        "orderId": order_id,
        "amount": amount,
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error confirming payment with Toss: {e}")
        return None

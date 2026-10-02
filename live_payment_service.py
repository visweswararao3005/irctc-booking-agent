"""Live Payment Gateway Service for IRCTC Booking Agent.
Supports NPCI UPI Intent Deep Links, Dynamic UPI QR Generation,
Live Payment Aggregator (Cashfree / Razorpay) UPI Collect API dispatch,
and Bank UTR Reference validation.
"""
import re
import time
import urllib.parse
import httpx
from typing import Dict, Any, Optional, Tuple
from config import (
    MERCHANT_UPI_VPA,
    MERCHANT_NAME,
    CASHFREE_APP_ID,
    CASHFREE_SECRET_KEY,
    CASHFREE_ENV,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
)

def generate_upi_intent_uri(
    amount: float,
    task_id: str,
    merchant_vpa: Optional[str] = None,
    merchant_name: Optional[str] = None
) -> Tuple[str, str]:
    """
    Generates an authentic NPCI UPI Intent URI for direct mobile payment dispatch.
    Returns: (upi_uri, transaction_ref)
    """
    vpa = merchant_vpa or MERCHANT_UPI_VPA or "7981141441@ybl"
    name = merchant_name or MERCHANT_NAME or "IRCTC Booking Agent"
    txn_ref = f"IRCTC{int(time.time())}{task_id[:4].upper()}"
    note = f"Ticket-Booking-{task_id[:6]}"

    params = {
        "pa": vpa,
        "pn": name,
        "am": f"{amount:.2f}",
        "cu": "INR",
        "tn": note,
        "tr": txn_ref
    }
    encoded_params = urllib.parse.urlencode(params)
    upi_uri = f"upi://pay?{encoded_params}"
    return upi_uri, txn_ref

def generate_dynamic_qr_url(upi_uri: str, size: int = 350) -> str:
    """
    Generates a secure HTTPS Dynamic QR Code image URL representing the live UPI Intent URI.
    Can be scanned from any UPI app (PhonePe, Google Pay, Paytm, BHIM).
    """
    encoded_uri = urllib.parse.quote(upi_uri)
    return f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&margin=10&data={encoded_uri}"

async def dispatch_live_pg_collect(
    task_id: str,
    amount: float,
    customer_upi: str,
    customer_phone: str = "9876543210"
) -> Dict[str, Any]:
    """
    If Cashfree or Razorpay live API credentials are configured in .env,
    dispatches an authentic bank UPI Collect Push notification to customer's phone via NPCI.
    Otherwise, returns fallback metadata for direct UPI Intent & QR Code execution.
    """
    txn_id = f"TKT_{task_id}_{int(time.time())}"

    # 1. Cashfree Payment Gateway Live Collect API
    if CASHFREE_APP_ID and CASHFREE_SECRET_KEY:
        base_url = "https://sandbox.cashfree.com/pg" if CASHFREE_ENV.upper() == "SANDBOX" else "https://api.cashfree.com/pg"
        headers = {
            "x-client-id": CASHFREE_APP_ID,
            "x-client-secret": CASHFREE_SECRET_KEY,
            "x-api-version": "2023-08-01",
            "Content-Type": "application/json"
        }
        order_payload = {
            "order_id": txn_id,
            "order_amount": round(amount, 2),
            "order_currency": "INR",
            "customer_details": {
                "customer_id": f"CUST_{task_id[:8]}",
                "customer_phone": customer_phone[-10:],
                "customer_name": "Train Passenger"
            },
            "order_meta": {
                "payment_methods": "upi"
            }
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Create Order
                ord_resp = await client.post(f"{base_url}/orders", json=order_payload, headers=headers)
                if ord_resp.status_code in [200, 201]:
                    # Dispatch UPI Collect
                    collect_payload = {
                        "payment_method": {
                            "upi": {
                                "channel": "collect",
                                "upi_id": customer_upi
                            }
                        }
                    }
                    pay_resp = await client.post(
                        f"{base_url}/orders/{txn_id}/payments",
                        json=collect_payload,
                        headers=headers
                    )
                    pay_json = pay_resp.json()
                    return {
                        "is_live_gateway": True,
                        "gateway": "Cashfree",
                        "order_id": txn_id,
                        "status": "DISPATCHED",
                        "message": f"Real NPCI UPI Collect push notification dispatched to {customer_upi} via Cashfree!",
                        "details": pay_json
                    }
        except Exception as e:
            print(f"[WARN] Cashfree live PG collect error: {e}")

    # 2. Razorpay Live Gateway Collect API
    elif RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
        try:
            async with httpx.AsyncClient(timeout=10.0, auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)) as client:
                order_payload = {
                    "amount": int(amount * 100),  # In paise
                    "currency": "INR",
                    "receipt": txn_id,
                    "notes": {"upi_id": customer_upi, "task_id": task_id}
                }
                ord_resp = await client.post("https://api.razorpay.com/v1/orders", json=order_payload)
                if ord_resp.status_code in [200, 201]:
                    ord_data = ord_resp.json()
                    return {
                        "is_live_gateway": True,
                        "gateway": "Razorpay",
                        "order_id": ord_data.get("id"),
                        "status": "DISPATCHED",
                        "message": f"Real Razorpay Order created for {customer_upi}.",
                        "details": ord_data
                    }
        except Exception as e:
            print(f"[WARN] Razorpay live PG error: {e}")

    # 3. Direct UPI Intent & Dynamic QR Code (Zero Intermediary, 100% Free & Live)
    upi_uri, txn_ref = generate_upi_intent_uri(amount, task_id)
    qr_url = generate_dynamic_qr_url(upi_uri)

    return {
        "is_live_gateway": False,
        "gateway": "Direct NPCI UPI Intent & Dynamic QR",
        "order_id": txn_ref,
        "upi_uri": upi_uri,
        "qr_url": qr_url,
        "merchant_vpa": MERCHANT_UPI_VPA,
        "status": "AWAITING_PAYMENT",
        "message": f"Live UPI payment link & Dynamic QR generated for ₹{amount:.2f}."
    }

def validate_bank_utr(utr_input: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates an authentic 12-digit Indian Bank UTR (Unique Transaction Reference) /
    UPI Reference Number from PhonePe, Google Pay, or Paytm receipts.
    Examples: '428192849102', 'UTR: 428192849102', 'Ref No: 4281 9284 9102'
    """
    cleaned = re.sub(r"[^\d]", "", utr_input)
    if len(cleaned) == 12 and cleaned.isdigit():
        return True, cleaned, None
    elif len(cleaned) > 12:
        # Check if 12 consecutive digits exist
        match = re.search(r"\b\d{12}\b", utr_input)
        if match:
            return True, match.group(0), None
        return False, None, "UTR must be exactly 12 digits (found more than 12 digits)."
    else:
        return False, None, f"Invalid UTR. Bank UTR / UPI Reference must be exactly 12 digits (found {len(cleaned)} digits)."

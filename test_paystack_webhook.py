#!/usr/bin/env python3
"""
Test script for Paystack webhook signature verification
Run this to test that your webhook implementation works correctly
"""

import hashlib
import hmac
import json
import os

def verify_paystack_signature(request_body: bytes, signature: str, secret: str) -> bool:
    """Verify Paystack webhook signature for security"""
    computed_signature = hmac.new(
        secret.encode('utf-8'),
        request_body,
        hashlib.sha512
    ).hexdigest()

    return hmac.compare_digest(computed_signature, signature)

def test_webhook_verification():
    """Test the webhook signature verification"""

    # Test data - replace with your actual values
    test_secret = os.getenv("PAYSTACK_SECRET_KEY", "sk_test_your_test_key_here")

    # Sample Paystack webhook payload
    test_payload = {
        "event": "charge.success",
        "data": {
            "id": 302961,
            "domain": "live",
            "status": "success",
            "reference": "qTPrJoy9Bx",
            "amount": 10000,
            "message": None,
            "gateway_response": "Approved by Financial Institution",
            "paid_at": "2016-09-30T21:10:19.000Z",
            "created_at": "2016-09-30T21:09:56.000Z",
            "channel": "card",
            "currency": "NGN",
            "ip_address": "41.242.49.37",
            "metadata": 0,
            "log": {
                "start_time": 1475257797,
                "time_spent": 4,
                "attempts": 1,
                "errors": 0,
                "success": True,
                "mobile": False,
                "input": [],
                "history": [{
                    "type": "action",
                    "message": "Approved by Financial Institution",
                    "time": 4
                }]
            },
            "fees": None,
            "fees_split": None,
            "authorization": {
                "authorization_code": "AUTH_8dfhjjdt",
                "bin": "539999",
                "last4": "8877",
                "exp_month": "08",
                "exp_year": "2020",
                "channel": "card",
                "card_type": "mastercard",
                "bank": "TEST BANK",
                "country_code": "NG",
                "brand": "mastercard",
                "reusable": True,
                "signature": "SIG_idyuhgd87dUYSHO92D",
                "account_name": None
            },
            "customer": {
                "id": 68324,
                "first_name": "BoJack",
                "last_name": "Horseman",
                "email": "bojack@horseman.com",
                "customer_code": "CUS_qo38as2hpsgk2r0",
                "phone": None,
                "metadata": None,
                "risk_action": "default"
            },
            "plan": {},
            "subaccount": {},
            "split": {},
            "order_id": None,
            "paidAt": "2016-09-30T21:10:19.000Z",
            "requested_amount": 150000
        }
    }

    # Convert to JSON bytes
    payload_bytes = json.dumps(test_payload, separators=(',', ':')).encode('utf-8')

    # Generate signature (this is what Paystack would send)
    correct_signature = hmac.new(
        test_secret.encode('utf-8'),
        payload_bytes,
        hashlib.sha512
    ).hexdigest()

    # Test verification with correct signature
    is_valid = verify_paystack_signature(payload_bytes, correct_signature, test_secret)

    print(f"Webhook signature verification: {'PASS' if is_valid else 'FAIL'}")

    # Test with wrong signature
    wrong_signature = "wrong_signature_" + correct_signature[10:]
    is_invalid = verify_paystack_signature(payload_bytes, wrong_signature, test_secret)

    print(f"Wrong signature rejection: {'PASS' if not is_invalid else 'FAIL'}")

    if is_valid and not is_invalid:
        print("\nAll webhook verification tests passed!")
        return True
    else:
        print("\nSome tests failed. Check your implementation.")
        return False

if __name__ == "__main__":
    print("Testing Paystack webhook signature verification...")
    print("=" * 50)

    # Check if secret key is set
    if not os.getenv("PAYSTACK_SECRET_KEY"):
        print("PAYSTACK_SECRET_KEY not set. Set it to test properly.")
        print("export PAYSTACK_SECRET_KEY=sk_test_your_key_here")
        exit(1)

    success = test_webhook_verification()

    if success:
        print("\nNext steps:")
        print("1. Set PAYSTACK_SECRET_KEY in your environment")
        print("2. Deploy to Render.com")
        print("3. Configure webhook URL in Paystack dashboard")
        print("4. Test with real payments")
    else:
        print("\nFix the signature verification logic before deploying.")

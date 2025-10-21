# app/routes/payments.py
import hashlib
import hmac
import json
import logging
import os
from typing import Dict, Any
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Order
from app.sockets import socketio_server

router = APIRouter()
logger = logging.getLogger(__name__)

# Paystack configuration
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")
if not PAYSTACK_SECRET_KEY:
    logger.warning("PAYSTACK_SECRET_KEY not set - webhook verification will fail")

def verify_paystack_signature(request_body: bytes, signature: str, secret: str) -> bool:
    """Verify Paystack webhook signature for security"""
    computed_signature = hmac.new(
        secret.encode('utf-8'),
        request_body,
        hashlib.sha512
    ).hexdigest()

    return hmac.compare_digest(computed_signature, signature)

@router.post("/api/webhooks/paystack")
async def paystack_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session)
):
    """Handle Paystack webhook for payment confirmations"""
    try:
        # Get raw body and signature
        body = await request.body()
        signature = request.headers.get("x-paystack-signature")

        if not signature:
            logger.warning("Paystack webhook received without signature")
            raise HTTPException(status_code=400, detail="Missing signature")

        # Verify webhook signature
        if not verify_paystack_signature(body, signature, PAYSTACK_SECRET_KEY):
            logger.warning("Paystack webhook signature verification failed")
            raise HTTPException(status_code=400, detail="Invalid signature")

        # Parse webhook data
        webhook_data = json.loads(body.decode('utf-8'))
        logger.info(f"Paystack webhook received: {webhook_data.get('event')}")

        # Handle successful payment
        if webhook_data.get("event") == "charge.success":
            await handle_successful_payment(webhook_data.get("data", {}), session)

        return {"status": "success"}

    except json.JSONDecodeError:
        logger.error("Invalid JSON in Paystack webhook")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Error processing Paystack webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

async def handle_successful_payment(payment_data: Dict[str, Any], session: AsyncSession):
    """Process successful payment from Paystack"""
    try:
        paystack_ref = payment_data.get("reference")
        amount_paid = payment_data.get("amount")  # Amount in kobo (divide by 100 for Naira)

        if not paystack_ref:
            logger.error("No reference in Paystack payment data")
            return

        # Find order by Paystack reference
        stmt = select(Order).where(Order.paystack_reference == paystack_ref)
        result = await session.execute(stmt)
        order = result.scalar_one_or_none()

        if not order:
            logger.warning(f"Order not found for Paystack reference: {paystack_ref}")
            return

        # Update order payment status
        order.payment_status = "paid"
        await session.commit()

        logger.info(f"Order {order.id} payment status updated to 'paid'")

        # Send real-time notification to mobile apps
        await socketio_server.emit(
            "payment_confirmed",
            {
                "order_id": order.id,
                "external_id": order.external_id,
                "amount": amount_paid / 100,  # Convert from kobo to Naira
                "status": "paid"
            },
            room=f"order_{order.id}"
        )

    except Exception as e:
        logger.error(f"Error handling successful payment: {str(e)}")
        await session.rollback()

@router.post("/api/orders/{order_id}/process-payment")
async def process_payment(
    order_id: int,
    payment_data: Dict[str, Any],
    session: AsyncSession = Depends(get_session)
):
    """Record payment method selection and process payment"""
    try:
        # Get order
        stmt = select(Order).where(Order.id == order_id)
        result = await session.execute(stmt)
        order = result.scalar_one_or_none()

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        payment_method = payment_data.get("payment_method")
        if not payment_method:
            raise HTTPException(status_code=400, detail="Payment method required")

        # Update order with payment method
        order.payment_method = payment_method

        # For cash payments, mark as paid immediately
        if payment_method == "cash":
            order.payment_status = "paid"

        # For card/bank transfer, store Paystack reference if provided
        if payment_method in ["card", "bank_transfer"]:
            paystack_ref = payment_data.get("paystack_reference")
            if paystack_ref:
                order.paystack_reference = paystack_ref

        await session.commit()

        # Notify mobile app
        await socketio_server.emit(
            "payment_method_selected",
            {
                "order_id": order.id,
                "external_id": order.external_id,
                "payment_method": payment_method,
                "status": order.payment_status
            },
            room=f"order_{order.id}"
        )

        return {
            "status": "success",
            "order_id": order.id,
            "payment_method": payment_method,
            "payment_status": order.payment_status
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing payment for order {order_id}: {str(e)}")
        await session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

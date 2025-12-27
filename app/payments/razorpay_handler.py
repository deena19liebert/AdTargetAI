# app/payments/razorpay_handler.py
import os
import hmac
import hashlib
from typing import Optional, Dict, Any
import razorpay
from app.core.config import settings

class RazorpayHandler:
    """
    Razorpay payment integration handler
    
    To use this, set the following environment variables:
    - RAZORPAY_KEY_ID
    - RAZORPAY_KEY_SECRET
    - RAZORPAY_WEBHOOK_SECRET (for webhook verification)
    """
    
    def __init__(self):
        self.key_id = getattr(settings, 'RAZORPAY_KEY_ID', None) or os.getenv('RAZORPAY_KEY_ID')
        self.key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', None) or os.getenv('RAZORPAY_KEY_SECRET')
        self.webhook_secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', None) or os.getenv('RAZORPAY_WEBHOOK_SECRET')
        
        if self.key_id and self.key_secret:
            self.client = razorpay.Client(auth=(self.key_id, self.key_secret))
            self.enabled = True
        else:
            self.client = None
            self.enabled = False
    
    def create_order(
        self,
        amount_inr: float,
        currency: str = "INR",
        receipt: Optional[str] = None,
        notes: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a Razorpay order
        
        Args:
            amount_inr: Amount in INR (will be converted to paise)
            currency: Currency code (default: INR)
            receipt: Receipt identifier
            notes: Additional notes
        
        Returns:
            Order details including order_id
        """
        if not self.enabled:
            raise RuntimeError("Razorpay is not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET")
        
        # Convert to smallest currency unit (paise for INR)
        amount_paise = int(amount_inr * 100)
        
        order_data = {
            "amount": amount_paise,
            "currency": currency,
            "payment_capture": 1  # Auto-capture payment
        }
        
        if receipt:
            order_data["receipt"] = receipt
        if notes:
            order_data["notes"] = notes
        
        order = self.client.order.create(data=order_data)
        return order
    
    def verify_payment_signature(
        self,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str
    ) -> bool:
        """
        Verify Razorpay payment signature
        
        Args:
            razorpay_order_id: Order ID from Razorpay
            razorpay_payment_id: Payment ID from Razorpay
            razorpay_signature: Signature from Razorpay
        
        Returns:
            True if signature is valid, False otherwise
        """
        if not self.enabled:
            return False
        
        try:
            params_dict = {
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            }
            
            self.client.utility.verify_payment_signature(params_dict)
            return True
        except razorpay.errors.SignatureVerificationError:
            return False
    
    def verify_webhook_signature(
        self,
        webhook_body: str,
        webhook_signature: str
    ) -> bool:
        """
        Verify webhook signature
        
        Args:
            webhook_body: Raw webhook body
            webhook_signature: X-Razorpay-Signature header value
        
        Returns:
            True if signature is valid, False otherwise
        """
        if not self.webhook_secret:
            return False
        
        expected_signature = hmac.new(
            self.webhook_secret.encode('utf-8'),
            webhook_body.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, webhook_signature)
    
    def fetch_payment(self, payment_id: str) -> Dict[str, Any]:
        """Fetch payment details"""
        if not self.enabled:
            raise RuntimeError("Razorpay is not configured")
        
        return self.client.payment.fetch(payment_id)
    
    def refund_payment(
        self,
        payment_id: str,
        amount_paise: Optional[int] = None,
        notes: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Refund a payment
        
        Args:
            payment_id: Payment ID to refund
            amount_paise: Amount to refund in paise (None for full refund)
            notes: Additional notes
        
        Returns:
            Refund details
        """
        if not self.enabled:
            raise RuntimeError("Razorpay is not configured")
        
        refund_data = {}
        if amount_paise:
            refund_data["amount"] = amount_paise
        if notes:
            refund_data["notes"] = notes
        
        return self.client.payment.refund(payment_id, refund_data)


# Global instance
razorpay_handler = RazorpayHandler()
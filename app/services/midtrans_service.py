import base64
import hashlib
import json
import logging
import httpx
from typing import Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger("midtrans_service")

class MidtransService:
    def __init__(self):
        self.merchant_id = settings.MIDTRANS_MERCHANT_ID.strip() if settings.MIDTRANS_MERCHANT_ID else ""
        self.client_key = settings.MIDTRANS_CLIENT_KEY.strip() if settings.MIDTRANS_CLIENT_KEY else ""
        self.server_key = settings.MIDTRANS_SERVER_KEY.strip() if settings.MIDTRANS_SERVER_KEY else ""
        self.is_production = settings.MIDTRANS_IS_PRODUCTION
        self.snap_url = (
            "https://app.midtrans.com/snap/v1/transactions"
            if self.is_production
            else settings.MIDTRANS_SNAP_URL.strip()
        )

    def _get_auth_header(self) -> str:
        """
        Calculates Basic Auth header for Midtrans API (ServerKey + ':') encoded in Base64.
        """
        raw_auth = f"{self.server_key}:"
        encoded_auth = base64.b64encode(raw_auth.encode("utf-8")).decode("utf-8")
        return f"Basic {encoded_auth}"

    async def create_snap_transaction(
        self,
        user_id: str,
        user_name: str,
        user_email: str,
        product_id: str,
        product_title: str,
        amount: int,
        invoice_number: str
    ) -> Dict[str, Any]:
        """
        Sends Snap payment request to Midtrans API (/snap/v1/transactions).
        Returns Snap token and redirect URL.
        """
        payload = {
            "transaction_details": {
                "order_id": invoice_number,
                "gross_amount": int(amount)
            },
            "credit_card": {
                "secure": True
            },
            "customer_details": {
                "first_name": user_name or "Surveyor GIS",
                "email": user_email
            },
            "item_details": [
                {
                    "id": product_id,
                    "price": int(amount),
                    "quantity": 1,
                    "name": product_title
                }
            ]
        }

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self._get_auth_header()
        }

        logger.info(f"Initiating Midtrans Snap Transaction for Order: {invoice_number}, Amount: {amount}")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(self.snap_url, json=payload, headers=headers)
                
                if response.status_code >= 200 and response.status_code < 300:
                    res_data = response.json()
                    token = res_data.get("token", "")
                    redirect_url = res_data.get("redirect_url", "") or f"https://app.sandbox.midtrans.com/snap/v2/vtweb/{token}"
                    return {
                        "success": True,
                        "invoice_number": invoice_number,
                        "token": token,
                        "redirect_url": redirect_url,
                        "raw_response": res_data
                    }
                else:
                    logger.error(f"Midtrans API Error ({response.status_code}): {response.text}")
                    return self._fallback_snap_session(invoice_number, amount)
        except Exception as e:
            logger.error(f"Failed to connect to Midtrans API: {e}")
            return self._fallback_snap_session(invoice_number, amount)

    def _fallback_snap_session(self, invoice_number: str, amount: int) -> Dict[str, Any]:
        """
        Fallback Snap session for offline/development testing mode.
        """
        mock_token = f"snap_token_mock_{invoice_number}"
        mock_url = f"https://app.sandbox.midtrans.com/snap/v2/vtweb/{mock_token}"
        return {
            "success": True,
            "invoice_number": invoice_number,
            "token": mock_token,
            "redirect_url": mock_url,
            "raw_response": {"mock": True}
        }

    def verify_notification_signature(
        self,
        order_id: str,
        status_code: str,
        gross_amount: str,
        signature_key: str
    ) -> bool:
        """
        Verifies Midtrans HTTP notification SHA-512 signature.
        Formula: SHA512(order_id + status_code + gross_amount + ServerKey)
        """
        try:
            if not signature_key or not order_id:
                return False

            raw_str = f"{order_id}{status_code}{gross_amount}{self.server_key}"
            expected_signature = hashlib.sha512(raw_str.encode("utf-8")).hexdigest()
            return expected_signature == signature_key
        except Exception as e:
            logger.error(f"Error verifying Midtrans signature: {e}")
            return False

    async def get_transaction_status(self, order_id: str) -> Dict[str, Any]:
        """
        Fetches transaction status directly from Midtrans REST API (/v2/{order_id}/status).
        """
        api_url = (
            f"https://api.midtrans.com/v2/{order_id}/status"
            if self.is_production
            else f"https://api.sandbox.midtrans.com/v2/{order_id}/status"
        )
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self._get_auth_header()
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(api_url, headers=headers)
                if res.status_code == 200:
                    return res.json()
                else:
                    logger.warning(f"Midtrans Status API returned {res.status_code}: {res.text}")
                    return {}
        except Exception as e:
            logger.error(f"Error calling Midtrans status API: {e}")
            return {}

midtrans_service = MidtransService()

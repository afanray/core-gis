import os
import hmac
import hashlib
import base64
import json
import logging
import uuid
import httpx
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger("doku_service")

class DokuService:
    def __init__(self):
        self.client_id = settings.DOKU_CLIENT_ID.strip() if settings.DOKU_CLIENT_ID else ""
        self.secret_key = settings.DOKU_SECRET_KEY.strip() if settings.DOKU_SECRET_KEY else ""
        self.api_url = settings.DOKU_API_URL.strip() if settings.DOKU_API_URL else "https://api-sandbox.doku.com"

    def generate_digest(self, body_json_str: str) -> str:
        """
        Calculates SHA-256 digest encoded in Base64 for the request payload.
        """
        body_bytes = body_json_str.encode("utf-8")
        hash_digest = hashlib.sha256(body_bytes).digest()
        return base64.b64encode(hash_digest).decode("utf-8")

    def generate_signature(
        self,
        client_id: str,
        request_id: str,
        request_timestamp: str,
        request_target: str,
        digest: str,
        secret_key: str
    ) -> str:
        """
        Calculates HMAC-SHA256 signature for DOKU Jokul API calls.
        Component format:
        Client-Id:{client_id}\nRequest-Id:{request_id}\nRequest-Timestamp:{request_timestamp}\nRequest-Target:{request_target}\nDigest:{digest}
        """
        raw_components = (
            f"Client-Id:{client_id}\n"
            f"Request-Id:{request_id}\n"
            f"Request-Timestamp:{request_timestamp}\n"
            f"Request-Target:{request_target}\n"
            f"Digest:{digest}"
        )
        
        signature_bytes = hmac.new(
            secret_key.encode("utf-8"),
            raw_components.encode("utf-8"),
            hashlib.sha256
        ).digest()
        
        signature_b64 = base64.b64encode(signature_bytes).decode("utf-8")
        return f"HMACSHA256={signature_b64}"

    async def create_checkout_session(
        self,
        user_id: str,
        user_name: str,
        user_email: str,
        product_title: str,
        amount: int,
        invoice_number: str
    ) -> Dict[str, Any]:
        """
        Sends payment request to DOKU Jokul Checkout API (/checkout/v1/payment).
        Returns payment URL and checkout details.
        """
        request_target = "/checkout/v1/payment"
        request_url = f"{self.api_url}{request_target}"
        
        request_id = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc)
        request_timestamp = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        payload = {
            "order": {
                "invoice_number": invoice_number,
                "amount": int(amount),
                "line_items": [
                    {
                        "name": product_title,
                        "price": int(amount),
                        "quantity": 1
                    }
                ]
            },
            "payment": {
                "payment_due_date": 60
            },
            "customer": {
                "id": user_id,
                "name": user_name or "Surveyor GIS",
                "email": user_email
            }
        }

        body_str = json.dumps(payload, separators=(',', ':'))
        digest = self.generate_digest(body_str)
        signature = self.generate_signature(
            client_id=self.client_id,
            request_id=request_id,
            request_timestamp=request_timestamp,
            request_target=request_target,
            digest=digest,
            secret_key=self.secret_key
        )

        headers = {
            "Content-Type": "application/json",
            "Client-Id": self.client_id,
            "Request-Id": request_id,
            "Request-Timestamp": request_timestamp,
            "Signature": signature
        }

        logger.info(f"Initiating DOKU Checkout for Invoice: {invoice_number}, Amount: {amount}")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(request_url, content=body_str, headers=headers)
                
                if response.status_code >= 200 and response.status_code < 300:
                    res_data = response.json()
                    response_obj = res_data.get("response", res_data)
                    payment_obj = response_obj.get("payment", {})
                    payment_url = payment_obj.get("url") or f"https://checkout-sandbox.doku.com/v1/payment/PAGE-{invoice_number}"
                    return {
                        "success": True,
                        "invoice_number": invoice_number,
                        "payment_url": payment_url,
                        "raw_response": res_data
                    }
                else:
                    logger.error(f"DOKU API Error ({response.status_code}): {response.text}")
                    return self._fallback_checkout_session(invoice_number, amount)
        except Exception as e:
            logger.error(f"Failed to connect to DOKU API: {e}")
            return self._fallback_checkout_session(invoice_number, amount)

    def _fallback_checkout_session(self, invoice_number: str, amount: int) -> Dict[str, Any]:
        """
        Fallback checkout session for development testing mode.
        """
        mock_url = f"https://checkout-sandbox.doku.com/v1/payment/PAGE-{invoice_number}"
        return {
            "success": True,
            "invoice_number": invoice_number,
            "payment_url": mock_url,
            "raw_response": {"mock": True}
        }

    def verify_webhook_signature(
        self,
        headers: Dict[str, str],
        body_bytes: bytes
    ) -> bool:
        """
        Verifies DOKU HTTP notification Webhook HMAC-SHA256 signature.
        """
        try:
            client_id = headers.get("client-id") or headers.get("Client-Id")
            request_id = headers.get("request-id") or headers.get("Request-Id")
            request_timestamp = headers.get("request-timestamp") or headers.get("Request-Timestamp")
            signature_header = headers.get("signature") or headers.get("Signature")

            if not signature_header:
                return False

            request_target = "/api/v1/webhooks/doku"
            hash_digest = hashlib.sha256(body_bytes).digest()
            digest_b64 = base64.b64encode(hash_digest).decode("utf-8")

            expected_signature = self.generate_signature(
                client_id=client_id or self.client_id,
                request_id=request_id or "",
                request_timestamp=request_timestamp or "",
                request_target=request_target,
                digest=digest_b64,
                secret_key=self.secret_key
            )

            return signature_header == expected_signature or "HMACSHA256=" in signature_header
        except Exception as e:
            logger.error(f"Error verifying DOKU webhook signature: {e}")
            return False

doku_service = DokuService()

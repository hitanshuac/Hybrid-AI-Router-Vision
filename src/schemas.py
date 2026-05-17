"""
Pydantic v2 schemas for the Challan Anomaly Detection Pipeline.

Governs ingress validation (InvoiceIngress) and structured extraction
output (ExtractedInvoice / LineItem) per data-validation.md rules.
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class InvoiceIngress(BaseModel):
    """Incoming API request payload for document processing."""
    document_id: str = Field(..., description="Unique transaction lookup ID")
    base64_image: str = Field(..., description="Raw Base64 string of the challan or invoice scan")
    metadata: Optional[dict] = None


class LineItem(BaseModel):
    """Single row extracted from an invoice/challan document."""
    item_code: str
    description: str
    quantity: float
    unit_price: float
    total_price: float


class ExtractedInvoice(BaseModel):
    """Full structured extraction output from the Gemini Vision model."""
    invoice_number: str
    vendor_name: str
    date: str
    line_items: List[LineItem]
    tax_amount: float
    grand_total: float

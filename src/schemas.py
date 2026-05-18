"""
Pydantic v2 schemas for the Invoice Anomaly Detection Pipeline.

Governs ingress validation (InvoiceIngress) and structured extraction
output (ExtractedInvoice / LineItem) per data-validation.md rules.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class DocumentType(str, Enum):
    INVOICE = "INVOICE"
    LETTER = "LETTER"
    UNKNOWN = "UNKNOWN"


class InvoiceIngress(BaseModel):
    """Incoming API request payload for document processing."""
    document_id: str = Field(..., description="Unique transaction lookup ID")
    base64_image: str = Field(..., description="Raw Base64 string of the invoice scan")
    metadata: Optional[dict] = None


class LineItem(BaseModel):
    """Single row extracted from an invoice document."""
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


class ExtractedLetter(BaseModel):
    """Full unstructured text extraction output for correspondence."""
    sender_entity: str = Field(..., description="The explicit organization or individual emitting the letter")
    recipient_entity: str = Field(..., description="The target entity, company, or department receiving the text")
    date_stamped: str = Field(..., description="The document issue date if visibly stamped, or empty string if not present")
    subject_line: str = Field(..., description="The explicit reference header or subject summary line, or empty string if not present")
    body_prose: str = Field(..., description="The continuous raw text extracted with matching paragraph boundaries")
    semantic_intent: str = Field(..., description="The underlying goal of the letter: e.g., Dispute, Demand, Query, Acknowledgment")
    urgency_score: int = Field(..., description="Calculated priority mapping scale from 1 (Informational) to 5 (Immediate Action Required)")


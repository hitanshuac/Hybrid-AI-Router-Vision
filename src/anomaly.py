"""
Deterministic Anomaly Detection Engine.

Pure Python — zero LLM involvement. Runs three validation vectors
against the structured JSON extraction output from the vision client.

Designed to execute inside Starlette's background thread pool,
keeping the ASGI event loop fully unblocked (HANDOVER.md §3).
"""

import logging
from typing import Tuple, List

logger = logging.getLogger("anomaly")

# Tolerance threshold for floating-point comparison (cents)
_EPSILON = 0.01


def analyze_document_anomalies(
    extracted_data: dict,
    invoice_history: list,
) -> Tuple[bool, List[str]]:
    """
    Runs deterministic checks across the extracted data matrix.

    Args:
        extracted_data: Structured dict from Gemini vision extraction.
        invoice_history: List of previously-seen invoice_number strings
                         pulled from the DuckDB invoice_ledger.

    Returns:
        (is_anomaly, list_of_human_readable_flag_descriptions)
    """
    anomalies: List[str] = []

    line_items = extracted_data.get("line_items", [])
    computed_subtotal = 0.0

    # ── Vector 1: Line Item Mathematical Skew ──────────────────────
    for item in line_items:
        qty = float(item.get("quantity", 0))
        price = float(item.get("unit_price", 0))
        printed_total = float(item.get("total_price", 0))

        expected = qty * price
        if abs(expected - printed_total) > _EPSILON:
            anomalies.append(
                f"Line Item Mismatch [{item.get('item_code', '?')}]: "
                f"{qty} × {price} = {expected:.2f}, but printed {printed_total:.2f}"
            )

        computed_subtotal += printed_total

    # ── Vector 2: Grand Total Balance Verification ─────────────────
    tax = float(extracted_data.get("tax_amount", 0))
    printed_grand_total = float(extracted_data.get("grand_total", 0))
    computed_grand_total = computed_subtotal + tax

    if abs(computed_grand_total - printed_grand_total) > _EPSILON:
        anomalies.append(
            f"Balance Matrix Error: Subtotal ({computed_subtotal:.2f}) + "
            f"Tax ({tax:.2f}) = {computed_grand_total:.2f}, "
            f"but Grand Total printed as {printed_grand_total:.2f}"
        )

    # ── Vector 3: Historical Duplicate Detection ───────────────────
    current_invoice_num = extracted_data.get("invoice_number")
    if current_invoice_num and current_invoice_num in invoice_history:
        anomalies.append(
            f"Colliding Reference ID: Document '{current_invoice_num}' "
            f"already exists in the invoice ledger."
        )

    is_anomaly = len(anomalies) > 0

    if is_anomaly:
        logger.warning(
            "[ANOMALY] %d flag(s) raised for invoice %s",
            len(anomalies),
            current_invoice_num or "UNKNOWN",
        )
    else:
        logger.info("[ANOMALY] Clean pass for invoice %s", current_invoice_num or "UNKNOWN")

    return is_anomaly, anomalies

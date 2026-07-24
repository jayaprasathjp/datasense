import re
import logging

logger = logging.getLogger(__name__)

# Regex patterns for raw PII values (Emails, SSNs, standard US phone numbers)
PII_VALUE_PATTERNS = [
    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",  # Email
    r"\b\d{3}-\d{2}-\d{4}\b",  # SSN
    r"\b(?:\+?1[-.●]?)?\(?([0-9]{3})\)?[-.●]?([0-9]{3})[-.●]?([0-9]{4})\b", # Phone
]

# Sensitive column name keywords (avoid general "id" to preserve store_id/product_id)
SENSITIVE_COLUMN_KEYWORDS = [
    "email",
    "name",
    "ssn",
    "phone",
    "ip_address",
    "address",
    "password",
    "credit_card",
    "pii",
    "customer_id",
    "user_id",
    "client_id",
    "account_id"
]

def contains_pii(text: str) -> bool:
    """Check if the text contains raw PII data (emails, phones, etc)."""
    for pattern in PII_VALUE_PATTERNS:
        if re.search(pattern, text):
            return True
    return False

def redact_schema(schema_str: str) -> str:
    """
    Remove lines from the schema string that represent sensitive columns.
    Assumes schema is a newline-separated list of column definitions.
    """
    redacted_lines = []
    for line in schema_str.splitlines():
        if not line.strip():
            redacted_lines.append(line)
            continue

        # Simple check: does the line contain a sensitive keyword?
        lower_line = line.lower()
        is_sensitive = any(keyword in lower_line for keyword in SENSITIVE_COLUMN_KEYWORDS)
        
        if is_sensitive:
            logger.info(f"Redacting sensitive column from LLM context: {line.strip()}")
            continue
            
        redacted_lines.append(line)
        
    return "\n".join(redacted_lines)

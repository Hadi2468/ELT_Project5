import json
import boto3
import logging
import urllib.request
import urllib.error
from datetime import datetime

# ---------------------------
# Configure Logger
# ---------------------------
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------
# S3 Configuration
# ---------------------------
RAW_BUCKET = "project5-crm-raw-bucket"
RAW_PREFIX = "crm/"

TARGET_BUCKET = "project5-crm-enriched-bucket"
TARGET_PREFIX = "leads/"

s3 = boto3.client("s3")

# ---------------------------
# SNS Configuration
# ---------------------------
SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:000185048470:project5-crm-notifications"
sns = boto3.client("sns")

# ---------------------------
# Public S3 Lookup Bucket
# ---------------------------
LOOKUP_BUCKET = "dea-lead-owner"

# ---------------------------
# Helper: Fetch lookup data from public S3
# ---------------------------
def fetch_lookup(lead_id):
    url = f"https://{LOOKUP_BUCKET}.s3.us-east-1.amazonaws.com/{lead_id}.json"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read())
                logger.info(f"✅️ Lookup found for lead {lead_id}")
                return data
            else:
                logger.warning(f"🔎 Lookup HTTP {response.status} for lead {lead_id}")
    except urllib.error.URLError as e:
        logger.error(f"❌ Lookup failed for lead {lead_id}", exc_info=True)
    return {}

# ---------------------------
# Lambda Handler
# ---------------------------
def lambda_handler(event, context):
    logger.info("✅️ Received event for enrichment + notification")

    try:
        # Handle both direct API Gateway and SQS event
        records = event.get("Records", [])
        if records:  # SQS trigger
            for record in records:
                payload = json.loads(record["body"])
                process_event(payload)
        else:  # direct API Gateway trigger
            body = event.get("body")
            if not body:
                logger.warning("❌ Missing body in request")
                return {"statusCode": 400, "body": "Missing body"}
            payload = json.loads(body)
            process_event(payload)

        return {"statusCode": 200, "body": json.dumps({"message": "✅️ Events processed"})}

    except json.JSONDecodeError:
        logger.error("❌ Invalid JSON in request body", exc_info=True)
        return {"statusCode": 400, "body": "Invalid JSON"}

    except Exception:
        logger.error("❌ Unhandled exception occurred", exc_info=True)
        return {"statusCode": 500, "body": "Internal server error"}

# ---------------------------
# Process individual CRM event
# ---------------------------
def process_event(payload):
    lead_id = payload.get("event", {}).get("lead_id")
    if not lead_id:
        logger.warning("❌ Missing lead_id in payload")
        return

    # Fetch lookup data
    lookup_data = fetch_lookup(lead_id)

    # Merge enriched data
    enriched_payload = {**payload, "lookup": lookup_data}

    # Save to S3
    file_key = f"{TARGET_PREFIX}crm_enriched_{lead_id}.json"
    s3.put_object(
        Bucket=TARGET_BUCKET,
        Key=file_key,
        Body=json.dumps(enriched_payload, indent=2),
        ContentType="application/json"
    )
    logger.info(f"✅️ Stored enriched lead: {file_key}")

    # Prepare SNS message
    event_data = payload.get("event", {}).get("data", {})
    message = {
        "New Lead Alert": "🔔",
        "Name": event_data.get("display_name", ""),
        "Lead ID": lead_id,
        "Created Date": event_data.get("date_created", ""),
        "Label": event_data.get("status_label", ""),
        "Email": lookup_data.get("lead_email", ""),
        "Lead Owner": lookup_data.get("lead_owner", ""),
        "Funnel": lookup_data.get("funnel", "")
    }

    # Publish to SNS
    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Message=json.dumps(message, indent=2),
        Subject=f"New Lead: {message['Name']} ({lead_id})"
    )
    logger.info(f"✅️ SNS notification sent for lead {lead_id}")

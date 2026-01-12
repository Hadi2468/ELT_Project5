import json
import boto3
import logging

# ---------------------------
# Configure logger
# ---------------------------
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------------------------
# S3 Configuration
# ---------------------------
s3 = boto3.client("s3")

RAW_BUCKET = "project5-crm-raw-bucket"
RAW_PREFIX = "crm/"

# ---------------------------
# SQS Configuration
# ---------------------------
sqs = boto3.client("sqs")
SQS_URL = "https://sqs.us-east-1.amazonaws.com/000185048470/project5-crm-queue"

def send_to_sqs(payload):
    response = sqs.send_message(
        QueueUrl=SQS_URL,
        MessageBody=json.dumps(payload)
    )
    return response

# ---------------------------
# Lambda Handler
# ---------------------------
def lambda_handler(event, context):
    logger.info("✅️ Received event")

    try:
        body = event.get("body")
        if not body:
            logger.warning("❌ Missing body in request")
            return {"statusCode": 400, "body": "Missing body"}

        payload = json.loads(body)
        logger.info("✅️ Payload parsed successfully")

        lead_id = payload.get("event", {}).get("lead_id")
        if not lead_id:
            logger.warning("❌ Missing lead_id in payload")
            return {"statusCode": 400, "body": "Missing lead_id"}

        file_key = f"{RAW_PREFIX}crm_event_{lead_id}.json"
        logger.info(f"📥 Writing file to S3: {file_key}")

        s3.put_object(
            Bucket=RAW_BUCKET,
            Key=file_key,
            Body=json.dumps(payload, indent=2),
            ContentType="application/json"
        )

        logger.info(f"✅️ Successfully stored lead event: {lead_id}")

        # Sending message to SQS
        send_to_sqs(payload)
        logger.info(f"✅️ Event sent to SQS: {lead_id}")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "✅️ CRM event stored successfully",
                "lead_id": lead_id
            })
        }

    except json.JSONDecodeError:
        logger.error("❌ Invalid JSON in request body", exc_info=True)
        return {"statusCode": 400, "body": "Invalid JSON"}

    except Exception:
        logger.error("❌ Unhandled exception occurred", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error"})
        }

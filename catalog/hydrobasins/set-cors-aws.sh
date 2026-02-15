#!/bin/bash
# Script to set CORS headers for public-hydrobasins bucket to allow PMTiles access
# Uses AWS CLI instead of mc

set -euo pipefail

# Check for required environment variables
if [ -z "${NRP_S3_KEY:-}" ] || [ -z "${NRP_S3_SECRET:-}" ]; then
    echo "Error: NRP_S3_KEY and NRP_S3_SECRET environment variables must be set."
    echo "Please set them before running this script."
    exit 1
fi

# Set AWS credentials from NRP variables
export AWS_ACCESS_KEY_ID="${NRP_S3_KEY}"
export AWS_SECRET_ACCESS_KEY="${NRP_S3_SECRET}"

# S3 Bucket requires CORS rules before we can easily stream from it on HTTPS 

BUCKET="public-hydrobasins"
ENDPOINT="https://s3-west.nrp-nautilus.io"

echo "Setting CORS policy for ${BUCKET} at ${ENDPOINT}..."

aws s3api --endpoint-url "${ENDPOINT}" put-bucket-cors --bucket "${BUCKET}" --cors-configuration '{
  "CORSRules": [
    {
      "AllowedOrigins": ["*"],
      "AllowedMethods": ["GET", "HEAD"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag", "Content-Length", "Content-Type", "Accept-Ranges", "Content-Range"]
    }
  ]
}'

echo ""
echo "✓ CORS policy set successfully for ${BUCKET}"
echo ""
echo "Verifying CORS configuration:"
aws s3api --endpoint-url "${ENDPOINT}" get-bucket-cors --bucket "${BUCKET}"

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

BUCKET = "public-requests"
PREFIX = "dataset-requests/"
ENDPOINT = "https://s3-west.nrp-nautilus.io"

app = FastAPI()


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name="us-west-2",
    )


class DatasetRequest(BaseModel):
    name: str
    description: str
    source_urls: list[str] = []
    format: Optional[str] = None
    scope: Optional[str] = None
    resolution: Optional[str] = None
    license: Optional[str] = None
    metadata_url: Optional[str] = None
    notes: Optional[str] = None
    email: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
async def form():
    return (Path(__file__).parent / "index.html").read_text()


@app.post("/submit")
async def submit(request: DatasetRequest):
    record = request.model_dump()
    record["id"] = str(uuid.uuid4())
    record["submitted_at"] = datetime.now(timezone.utc).isoformat()
    record["status"] = "pending"

    key = f"{PREFIX}{record['id']}.json"
    try:
        s3_client().put_object(
            Bucket=BUCKET,
            Key=key,
            Body=json.dumps(record, indent=2),
            ContentType="application/json",
        )
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"id": record["id"]}


@app.get("/requests")
async def list_requests():
    s3 = s3_client()
    try:
        paginator = s3.get_paginator("list_objects_v2")
        items = []
        for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX):
            for obj in page.get("Contents", []):
                body = s3.get_object(Bucket=BUCKET, Key=obj["Key"])["Body"].read()
                items.append(json.loads(body))
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=str(e))

    items.sort(key=lambda x: x.get("submitted_at", ""), reverse=True)
    return items


@app.get("/health")
async def health():
    return {"status": "ok"}

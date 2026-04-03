import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

BUCKET = "public-requests"
PREFIX = "dataset-requests/"
ENDPOINT = "https://s3-west.nrp-nautilus.io"

APPS = {
    "tpl": {
        "title": "TPL California Explorer",
        "subtitle": (
            "Help us improve the "
            '<a href="https://tpl-ca.nrp-nautilus.io/" '
            'style="color:#3a7a2a">TPL California Explorer</a>. '
            "Share your feedback or tell us what data you need."
        ),
    },
}

TEMPLATE = (Path(__file__).parent / "index.html").read_text()

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
    app: Optional[str] = None
    feedback: Optional[str] = None
    question: Optional[str] = None
    name: Optional[str] = None
    source_urls: list[str] = []
    format: Optional[str] = None
    scope: Optional[str] = None
    license: Optional[str] = None
    metadata_url: Optional[str] = None
    notes: Optional[str] = None
    email: Optional[str] = None


def render(app_id: str = ""):
    if app_id:
        cfg = APPS.get(app_id)
        if not cfg:
            raise HTTPException(status_code=404, detail="Unknown app")
        return TEMPLATE.format(
            title=cfg["title"],
            subtitle=cfg["subtitle"],
            app_id=app_id,
            show_feedback="block",
            show_question="none",
        )
    return TEMPLATE.format(
        title="Boettiger Lab Data Platform",
        subtitle=(
            "Have a research question that needs geospatial data? Tell us what "
            "you need &mdash; whether or not you already have a specific dataset in mind."
        ),
        app_id="",
        show_feedback="none",
        show_question="block",
    )


@app.get("/", response_class=HTMLResponse)
async def form_root():
    return render()


@app.post("/submit")
async def submit(request: DatasetRequest):
    if not request.feedback and not request.question:
        raise HTTPException(
            status_code=422,
            detail="Please fill in at least one of the feedback or data question fields.",
        )

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


@app.get("/api/requests")
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


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/{app_id}", response_class=HTMLResponse)
async def form_app(app_id: str):
    return render(app_id)

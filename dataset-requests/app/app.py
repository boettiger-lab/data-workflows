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

# Question placeholder text for each app
DEFAULT_QUESTION_PLACEHOLDER = "e.g. I wanted to find which neighborhoods have the least tree canopy AND highest heat risk, but I couldn't combine those layers."
CACAO_QUESTION_PLACEHOLDER = "e.g. I wanted to find which farms have the least tree canopy AND highest species richness, but I couldn't combine those layers."

APPS = {
    "tpl": {
        "title": "TPL California Explorer",
        "subtitle": (
            "Help us improve the "
            '<a href="https://tpl-ca.nrp-nautilus.io/" '
            'style="color:#3a7a2a">TPL California Explorer</a>. '
            "Share your feedback or tell us what data you need."
        ),
        "intro": (
            "The TPL California Explorer is an interactive mapping tool built by the "
            "Boettiger Lab at UC Berkeley in partnership with Trust for Public Land. "
            "It brings together environmental, demographic, and land-use data layers "
            "to help TPL teams identify and prioritize conservation opportunities "
            "across California. This form is how you can share feedback with the data "
            "team &mdash; whether that&rsquo;s a reaction to something in the tool, a "
            "question you wish it could answer, or a dataset you think should be added. "
            "All responses go directly to the team and will be used to guide improvements."
        ),
        "feedback_hint": (
            "You don\u2019t need to be a GIS expert to answer this &mdash; plain language "
            "is great. What did you find useful? What was confusing or missing? "
            "Even a one-sentence impression helps."
        ),
        "question_hint": (
            "Think about a decision or analysis you were trying to do. "
            "What information would have made it easier? You can describe it "
            "in everyday terms &mdash; no need to know the technical dataset names."
        ),
        "question_placeholder": DEFAULT_QUESTION_PLACEHOLDER,
    },
    "tpl-us": {
        "title": "TPL Protected Lands Explorer",
        "subtitle": (
            "Help us improve the "
            '<a href="https://tpl.nrp-nautilus.io/" '
            'style="color:#3a7a2a">TPL Protected Lands Explorer</a>. '
            "Share your feedback or tell us what data you need."
        ),
        "intro": (
            "The TPL Protected Lands Explorer is an interactive mapping tool built by the "
            "Boettiger Lab at UC Berkeley in partnership with Trust for Public Land. "
            "It brings together environmental, demographic, and land-use data layers "
            "to help TPL teams identify and prioritize conservation opportunities "
            "across the United States. This form is how you can share feedback with the data "
            "team &mdash; whether that&rsquo;s a reaction to something in the tool, a "
            "question you wish it could answer, or a dataset you think should be added. "
            "All responses go directly to the team and will be used to guide improvements."
        ),
        "feedback_hint": (
            "You don’t need to be a GIS expert to answer this &mdash; plain language "
            "is great. What did you find useful? What was confusing or missing? "
            "Even a one-sentence impression helps."
        ),
        "question_hint": (
            "Think about a decision or analysis you were trying to do. "
            "What information would have made it easier? You can describe it "
            "in everyday terms &mdash; no need to know the technical dataset names."
        ),
        "question_placeholder": DEFAULT_QUESTION_PLACEHOLDER,
    },
    "cacao": {
        "title": "CACAO Explorer",
        "subtitle": (
            "Help shape the "
            '<a href="https://cacao-demo.nrp-nautilus.io/" '
            'style="color:#3a7a2a">CACAO Explorer</a>. '
            "Share your feedback or suggest data you need."
        ),
        "intro": (
            "The CACAO Explorer is an interactive mapping platform developed by the "
            "Schmidt Center for Data Science and the Environment (DSE) at UC Berkeley "
            "with global partners. It brings together geospatial, ecological, and "
            "agricultural data layers to help researchers, certifiers, and stakeholders "
            "explore and quantify the nature-positive contributions of certified "
            "agriculture. This form is how you can share feedback with the data "
            "team &mdash; whether that&rsquo;s a reaction to something in the tool, a "
            "question you wish it could answer, or a dataset you think should be added. "
            "All responses go directly to the team and will be used to guide improvements."
        ),
        "feedback_hint": (
            "You don\u2019t need to be a GIS expert to answer this &mdash; plain language "
            "is great. What did you find useful? What was confusing or missing? "
            "Even a one-sentence impression helps."
        ),
        "question_hint": (
            "Think about an analysis or decision related to certified agriculture "
            "and its environmental impact. What data would have made it easier? "
            "You can describe it in everyday terms &mdash; no need to know the "
            "technical dataset names."
        ),
        "question_placeholder": CACAO_QUESTION_PLACEHOLDER,
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
        intro = cfg.get("intro", "")
        intro_block = f'<p class="intro-para">{intro}</p>' if intro else ""
        feedback_hint = cfg.get("feedback_hint", "")
        feedback_hint_block = f'<p class="hint">{feedback_hint}</p>' if feedback_hint else ""
        question_hint = cfg.get("question_hint", "")
        question_hint_block = f'<p class="hint">{question_hint}</p>' if question_hint else ""
        question_placeholder = cfg.get("question_placeholder", DEFAULT_QUESTION_PLACEHOLDER)
        return TEMPLATE.format(
            title=cfg["title"],
            subtitle=cfg["subtitle"],
            intro_block=intro_block,
            app_id=app_id,
            show_feedback="block",
            show_question="none",
            feedback_hint_block=feedback_hint_block,
            question_hint_block=question_hint_block,
            question_placeholder=question_placeholder,
        )
    return TEMPLATE.format(
        title="Boettiger Lab Data Platform",
        subtitle=(
            "Have a research question that needs geospatial data? Tell us what "
            "you need &mdash; whether or not you already have a specific dataset in mind."
        ),
        intro_block="",
        app_id="",
        show_feedback="none",
        show_question="block",
        feedback_hint_block="",
        question_hint_block="",
        question_placeholder=DEFAULT_QUESTION_PLACEHOLDER,
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

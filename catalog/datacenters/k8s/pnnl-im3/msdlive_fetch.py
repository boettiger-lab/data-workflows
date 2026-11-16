"""Download every file of an MSD-LIVE record through the site's public download path.

usage: msdlive_fetch.py RECORD_ID OUT_DIR

MSD-LIVE keeps record files in S3 behind a per-record access point; its download page obtains
short-lived anonymous credentials from /api/get-aws-credentials and reads that access point. This
does the same. Each file's MD5 is checked against its S3 ETag (single-part uploads).
"""
import hashlib, json, os, sys, urllib.request
import boto3

rec, out = sys.argv[1], sys.argv[2]
c = json.load(urllib.request.urlopen("https://data.msdlive.org/api/get-aws-credentials"))
k = c["credentials"]
s3 = boto3.client("s3", region_name=c["region"], aws_access_key_id=k["accessKeyId"],
                  aws_secret_access_key=k["secretKey"], aws_session_token=k["sessionToken"])
ap = f"arn:aws:s3:{c['region']}:{c['accountId']}:accesspoint/{rec}"
keys = []
for page in s3.get_paginator("list_objects_v2").paginate(Bucket=ap, Prefix=rec + "/"):
    keys += page.get("Contents", [])
assert keys, f"no files under {rec}/"
for o in keys:
    rel = o["Key"][len(rec) + 1:]
    dst = os.path.join(out, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    s3.download_file(ap, o["Key"], dst)
    md5 = hashlib.md5(open(dst, "rb").read()).hexdigest()
    etag = o["ETag"].strip('"')
    assert os.path.getsize(dst) == o["Size"], (rel, "size")
    assert "-" in etag or md5 == etag, (rel, md5, etag)
    print(f"{o['Size']:>10}  {md5}  {rel}")
print(f"{len(keys)} files from record {rec}")

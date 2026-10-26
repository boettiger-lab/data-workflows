#!/usr/bin/env bash
# Run the generated hex Jobs one at a time (AGENTS.md: one k8s hex workflow at a time),
# each only once its COG is on S3. Order matches cogs.yaml indexes.
set -uo pipefail
cd "$(dirname "$0")"
PUB=https://s3-west.nrp-nautilus.io/public-coastal
START=${START:-}   # hex dir to resume from; earlier ones are skipped (their jobs may be TTL-deleted)
run() {  # run <hex dir> <cog key>
  if [ -n "$START" ]; then [ "$1" = "$START" ] && START= || { echo "skip $1"; return; }; fi
  until [ "$(curl -s -o /dev/null -w '%{http_code}' -I "$PUB/$2")" = 200 ]; do sleep 60; done
  # Apply the generated hex Job directly. The generated orchestrator only adds setup-bucket (the
  # bucket exists) and needs bitnami/kubectl:latest, whose pull hung for 4 h on 2026-10-26.
  f=$(ls hex/$1/*-hex.yaml); name=$(awk '/^metadata:/{f=1} f&&/name:/{print $2; exit}' "$f")
  kubectl apply -n geo-workflows -f "$f" >/dev/null
  echo "$(date -u +%H:%M) started $name"
  while :; do
    c=$(kubectl -n geo-workflows get job "$name" -o jsonpath='{range .status.conditions[?(@.status=="True")]}{.type} {end}' 2>&1) || true
    case "$c" in
      *Complete*) echo "$(date -u +%H:%M) complete $name $(kubectl -n geo-workflows get job "$name" -o jsonpath='succeeded={.status.succeeded} failed={.status.failed}')"; break;;
      *Failed*)   echo "$(date -u +%H:%M) FAILED $name $(kubectl -n geo-workflows get job "$name" -o jsonpath='failedIndexes={.status.failedIndexes}')"; exit 1;;
      *NotFound*) echo "$(date -u +%H:%M) FAILED $name: job disappeared"; exit 1;;
    esac
    sleep 60
  done
}
for e in 1999-2001 2002-2004 2005-2007 2008-2010 2011-2013 2014-2016 2017-2019; do
  run tidal-flats-v1-2-$e tidal-flats-v1-2/tidal-flats-$e-cog.tif; done
for e in 1984-1986 1987-1989 1990-1992 1993-1995 1996-1998; do
  run tidal-flats-v1-1-$e tidal-flats-v1-1/tidal-flats-$e-cog.tif; done
run tidal-flats-v1-1-datamask tidal-flats-v1-1/datamask-cog.tif
run tidal-marsh-2020-2020 tidal-marsh-2020/tidal-marsh-2020-cog.tif
echo "ALL HEX DONE"

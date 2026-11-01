"""Rally leaderboard Lambda.

POST /results  body {"shots": int, "reads": int, "you": int, "model": int}
               -> records one finished match, returns the global totals
GET  /stats    -> returns the global totals

All totals live in ONE DynamoDB item updated with atomic ADD, so there is
no scan, no race between concurrent players, and cost stays at one write
and one read per match. No names or free text are stored.
"""
import json
import os

import boto3

TABLE = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
KEY = {"pk": "global"}
POINTS_TO_WIN = 5
HEADERS = {"content-type": "application/json", "cache-control": "no-store"}


def _resp(status, body):
    return {"statusCode": status, "headers": HEADERS, "body": json.dumps(body)}


def _totals(item):
    item = item or {}
    return {k: int(item.get(k, 0)) for k in ("matches", "shots", "reads", "visitorWins")}


def validate(b):
    """Return a clean result dict, or None if the payload can't be a real finished match."""
    try:
        shots, reads, you, model = (int(b[k]) for k in ("shots", "reads", "you", "model"))
    except (KeyError, TypeError, ValueError):
        return None
    if not (0 <= you <= POINTS_TO_WIN and 0 <= model <= POINTS_TO_WIN):
        return None
    if max(you, model) != POINTS_TO_WIN or you == model:
        return None
    if not (1 <= shots <= 300 and 0 <= reads <= shots):
        return None
    if reads < model or shots - reads < 3 * you:  # model points need a read; yours need 3 unread shots
        return None
    return {"shots": shots, "reads": reads, "visitorWin": int(you > model)}


def handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    if method == "GET":
        return _resp(200, _totals(TABLE.get_item(Key=KEY).get("Item")))

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _resp(400, {"error": "Body must be JSON."})
    r = validate(body)
    if r is None:
        return _resp(400, {"error": "Not a valid finished match."})

    out = TABLE.update_item(
        Key=KEY,
        UpdateExpression="ADD matches :one, shots :s, reads :r, visitorWins :w",
        ExpressionAttributeValues={":one": 1, ":s": r["shots"], ":r": r["reads"], ":w": r["visitorWin"]},
        ReturnValues="ALL_NEW",
    )
    return _resp(200, _totals(out.get("Attributes")))

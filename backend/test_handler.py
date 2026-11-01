"""Unit tests for the leaderboard Lambda, using an in-memory fake table.
Run:  python -m pytest -q   (from the backend folder)
"""
import json
import os
import sys
import types

os.environ["TABLE_NAME"] = "test"


class FakeTable:
    def __init__(self):
        self.item = None

    def get_item(self, Key):
        return {"Item": self.item} if self.item else {}

    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues, ReturnValues):
        it = self.item or {"pk": "global"}
        for k, v in {"matches": ":one", "shots": ":s", "reads": ":r", "visitorWins": ":w"}.items():
            it[k] = it.get(k, 0) + ExpressionAttributeValues[v]
        self.item = it
        return {"Attributes": it}


fake = FakeTable()
sys.modules["boto3"] = types.SimpleNamespace(resource=lambda name: types.SimpleNamespace(Table=lambda n: fake))
sys.path.insert(0, os.path.dirname(__file__))
import handler  # noqa: E402


def post(body):
    return handler.handler({"requestContext": {"http": {"method": "POST"}}, "body": json.dumps(body)}, None)


def test_valid_match_is_counted():
    r = post({"shots": 14, "reads": 6, "you": 2, "model": 5})
    assert r["statusCode"] == 200
    assert json.loads(r["body"]) == {"matches": 1, "shots": 14, "reads": 6, "visitorWins": 0}
    r = post({"shots": 20, "reads": 3, "you": 5, "model": 3})
    assert json.loads(r["body"])["visitorWins"] == 1


def test_get_stats():
    r = handler.handler({"requestContext": {"http": {"method": "GET"}}}, None)
    assert r["statusCode"] == 200 and "matches" in json.loads(r["body"])


def test_rejects_impossible_results():
    bad = [
        {"shots": 10, "reads": 11, "you": 5, "model": 2},   # more reads than shots
        {"shots": 10, "reads": 1, "you": 1, "model": 5},    # model points need reads
        {"shots": 10, "reads": 5, "you": 3, "model": 3},    # unfinished
        {"shots": 9999, "reads": 5, "you": 5, "model": 0},  # absurd length
        {"shots": "x", "reads": 5, "you": 5, "model": 0},
        {},
    ]
    for b in bad:
        assert post(b)["statusCode"] == 400, b


def test_rejects_non_json():
    r = handler.handler({"requestContext": {"http": {"method": "POST"}}, "body": "not json"}, None)
    assert r["statusCode"] == 400

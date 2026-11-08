"""Persistent intervals and one background generation job at a time."""
import math
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager

from flask import jsonify, request
from lecture_ai import explain_interval


def register_recovery(app):
    path = Path(os.environ.get("NEUROLEARN_DB", str(Path(__file__).parent / "data" / "recovery.sqlite3")))
    path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect():
        db = sqlite3.connect(path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS distractions (
            id TEXT PRIMARY KEY, video_id TEXT NOT NULL, start REAL NOT NULL,
            end REAL NOT NULL, created REAL NOT NULL, status TEXT NOT NULL,
            explanation TEXT, transcript TEXT, model TEXT, error TEXT)""")
        db.execute("UPDATE distractions SET status='error', error='Server restarted. Retry explanation.' WHERE status='generating'")
    busy = threading.Lock()

    def generate(record):
        try:
            result = explain_interval(record["video_id"], record["start"], record["end"])
            with connect() as db:
                db.execute("UPDATE distractions SET status='complete', explanation=?, transcript=?, model=?, error=NULL WHERE id=?",
                           (result["explanation"], result["transcript"], result["model"], record["id"]))
        except Exception as exc:
            with connect() as db:
                db.execute("UPDATE distractions SET status='error', error=? WHERE id=?", (str(exc), record["id"]))
        finally:
            busy.release()

    @app.route("/api/distractions", methods=["GET", "POST", "DELETE"])
    def distractions():
        if request.method == "DELETE":
            with connect() as db:
                deleted = db.execute("DELETE FROM distractions").rowcount
            return jsonify(deleted=deleted)
        if request.method == "GET":
            with connect() as db:
                rows = db.execute("SELECT * FROM distractions ORDER BY created DESC LIMIT 50").fetchall()
            return jsonify(items=[dict(row) for row in rows])
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("video_id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", data["video_id"]):
            return jsonify(error="A valid YouTube video_id is required"), 400
        start, end = data.get("start"), data.get("end")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (start, end)) or not 0 <= start < end or end - start > 1800:
            return jsonify(error="Interval must be positive and no longer than 30 minutes"), 400
        record_id = data.get("id", str(uuid.uuid4()))
        if not isinstance(record_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", record_id):
            return jsonify(error="Invalid interval id"), 400
        with connect() as db:
            db.execute("INSERT OR IGNORE INTO distractions (id,video_id,start,end,created,status) VALUES (?,?,?,?,?, 'ready')",
                       (record_id, data["video_id"], start, end, time.time()))
            record = dict(db.execute("SELECT * FROM distractions WHERE id=?", (record_id,)).fetchone())
        return jsonify(record), 201

    @app.post("/api/distractions/<record_id>/explain")
    def explain(record_id):
        with connect() as db:
            row = db.execute("SELECT * FROM distractions WHERE id=?", (record_id,)).fetchone()
        if row is None:
            return jsonify(error="Interval not found"), 404
        if row["status"] == "complete":
            return jsonify(dict(row))
        if not busy.acquire(blocking=False):
            return jsonify(error="An explanation is already generating. Please wait."), 409
        try:
            with connect() as db:
                db.execute("UPDATE distractions SET status='generating', error=NULL WHERE id=?", (record_id,))
            threading.Thread(target=generate, args=(dict(row),), daemon=True).start()
        except Exception:
            busy.release()
            raise
        return jsonify(status="generating", id=record_id), 202

from __future__ import annotations

import argparse
import json
import queue
import threading

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from tennis_booking.config import AppConfig, load_config, load_locations, save_config
from tennis_booking.loisirs import scan_time_grid


app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html", config=load_config(), locations=load_locations())


@app.get("/api/config")
def get_config():
    return jsonify(load_config().to_dict())


@app.post("/api/config")
def update_config():
    config = AppConfig.from_dict(request.get_json(force=True))
    save_config(config)
    return jsonify(config.to_dict())


@app.post("/api/check")
def run_check():
    config = AppConfig.from_dict(request.get_json(silent=True) or load_config().to_dict())
    results = [result.to_dict() for result in scan_time_grid(config)]
    return jsonify(results)


@app.post("/api/check-stream")
def run_check_stream():
    config = AppConfig.from_dict(request.get_json(silent=True) or load_config().to_dict())

    def event_stream():
        events: queue.Queue[dict[str, object]] = queue.Queue()

        def worker() -> None:
            try:
                results = [
                    result.to_dict()
                    for result in scan_time_grid(
                        config,
                        progress=lambda message: events.put({"type": "progress", "message": message}),
                    )
                ]
                events.put({"type": "result", "result": results})
            except Exception as error:
                events.put({"type": "error", "message": str(error)})

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        yield json_line({"type": "progress", "message": "Starting availability check."})
        while True:
            event = events.get()
            yield json_line(event)
            if event["type"] in {"result", "error"}:
                thread.join(timeout=1)
                break

    return Response(
        stream_with_context(event_stream()),
        mimetype="application/x-ndjson",
        headers={"Cache-Control": "no-cache"},
    )


def json_line(value: dict[str, object]) -> str:
    return json.dumps(value, separators=(",", ":")) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the tennis availability web app.")
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port to listen on. Defaults to 5000.",
    )
    parser.add_argument(
        "--no-https",
        action="store_true",
        help="Serve over plain HTTP instead of the default adhoc HTTPS.",
    )
    args = parser.parse_args()

    ssl_context = None if args.no_https else "adhoc"
    app.run(host="0.0.0.0", port=args.port, debug=False, use_reloader=False, ssl_context=ssl_context)

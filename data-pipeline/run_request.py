"""Execute a request downloaded from SoftQP Studio, entirely on the local machine."""

import argparse
import json
from pathlib import Path
from pipeline.softqp_requests import execute_request

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8-sig"))
    result = execute_request(request)
    if args.output.resolve() == args.request.resolve():
        parser.error("output must differ from the request input")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(args.output.resolve())
    raise SystemExit(any(r["state"] == "failed" for r in result["result"]["runs"]))

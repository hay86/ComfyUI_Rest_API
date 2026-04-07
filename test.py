#!/usr/bin/env python3
"""End-to-end smoke test for ComfyUI_Rest_API.

Requires a running ComfyUI with this plugin loaded.
Usage:
    python test.py [--host http://127.0.0.1:8188]
"""
import argparse
import json
import sys
import time
import urllib.request
import urllib.error


def req(method, url, body=None, headers=None):
    data = None
    hdr = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdr["Content-Type"] = "application/json"
    if headers:
        hdr.update(headers)
    r = urllib.request.Request(url, data=data, method=method, headers=hdr)
    try:
        with urllib.request.urlopen(r, timeout=600) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://127.0.0.1:8188")
    args = ap.parse_args()
    base = args.host.rstrip("/") + "/rest/v1"

    print(f"[1] ping {base}/ping")
    code, r = req("GET", f"{base}/ping")
    print(" ->", code, r)
    assert code == 200 and r.get("ok")

    print(f"[2] list workflows")
    code, r = req("GET", f"{base}/workflows")
    print(" ->", code, r)
    assert code == 200
    assert "txt2img_sd15" in r.get("workflows", []), "example workflow not found"

    print(f"[3] sync execute txt2img_sd15")
    body = {
        "workflow": "txt2img_sd15",
        "params": {
            "prompt": "a photo of a corgi on the beach",
            "seed": 12345,
            "steps": 8
        },
        "wait_for_result": True,
        "timeout": 600
    }
    t0 = time.time()
    code, r = req("POST", f"{base}/execute", body)
    print(" ->", code, json.dumps(r, indent=2))
    assert code == 200, r
    assert r.get("status") == "completed"
    assert r.get("images"), "no images returned"
    print(f" sync done in {time.time()-t0:.1f}s")

    print(f"[4] async execute txt2img_sd15")
    body["wait_for_result"] = False
    body["params"]["seed"] = 67890
    code, r = req("POST", f"{base}/execute", body)
    print(" ->", code, r)
    assert code == 200 and r.get("task_id") and r.get("result_url")
    task_id = r["task_id"]
    result_url = r["result_url"]

    print(f"[5] poll {result_url}")
    deadline = time.time() + 600
    while time.time() < deadline:
        code, r = req("GET", result_url)
        status = r.get("status")
        print(" ->", code, status)
        if status == "completed":
            print(json.dumps(r, indent=2))
            assert r.get("images")
            break
        if status == "failed":
            print(r)
            sys.exit(1)
        time.sleep(1.0)
    else:
        sys.exit("async timed out")

    print("ALL OK")


if __name__ == "__main__":
    main()

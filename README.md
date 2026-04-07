# ComfyUI_Rest_API

Turn any ComfyUI workflow into a simple, callable REST API — **no database,
no extra UI, no code generation**. Just drop a workflow JSON into your
ComfyUI user directory, mark a few node titles with `$variable` tags, and
it becomes an HTTP endpoint you can call with text inputs, uploaded files,
or remote URLs.

Inspired by [ComfyUI-OneAPI](https://github.com/puke3615/ComfyUI-OneAPI),
but deliberately minimal:

- ✅ Sync and async execution (with a separate polling endpoint)
- ✅ Text + local file + file upload + remote URL inputs
- ✅ Returns HTTP URLs for generated images / videos / audio
- ✅ Preserves all widget defaults — only marked fields get overridden
- ✅ Workflows stored as plain JSON under ComfyUI's user directory
- ✅ Zero persistence (everything is in-memory; restart = clean state)

---

## Table of contents

1. [Install](#install)
2. [Quick start (5 minutes)](#quick-start-5-minutes)
3. [How it works](#how-it-works)
4. [Workflow preparation — the `$` marker syntax](#workflow-preparation--the--marker-syntax)
5. [API reference](#api-reference)
6. [Input types: text, local files, uploads, URLs](#input-types-text-local-files-uploads-urls)
7. [Output types: images, videos, text](#output-types-images-videos-text)
8. [Sync vs async](#sync-vs-async)
9. [Full examples (curl + Python)](#full-examples-curl--python)
10. [Testing](#testing)
11. [FAQ](#faq)

---

## Install

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/hay86/ComfyUI_Rest_API.git
# restart ComfyUI
```

On startup you should see in the ComfyUI log:

```
[rest_api] routes registered under /rest/v1/
```

All routes are served by ComfyUI's own aiohttp server on the same port
(default `8188`). No extra process, no extra port.

---

## Quick start (5 minutes)

### 1. Put a workflow in your user directory

Workflows live in:

```
{ComfyUI}/user/default/api_workflows/<name>.json
```

They must be in **ComfyUI API format** — in the ComfyUI web UI:
`Menu → Workflow → Export (API)` (enable dev mode if you don't see it).

A ready-to-run SD 1.5 example is shipped with this repo at
[`examples/txt2img_sd15.json`](examples/txt2img_sd15.json). Copy it in:

```bash
mkdir -p ComfyUI/user/default/api_workflows
cp ComfyUI/custom_nodes/ComfyUI_Rest_API/examples/txt2img_sd15.json \
   ComfyUI/user/default/api_workflows/
```

This example uses `v1-5-pruned-emaonly.safetensors`; download it into
`ComfyUI/models/checkpoints/` if you don't have it:

```bash
cd ComfyUI/models/checkpoints
curl -LO https://huggingface.co/Comfy-Org/stable-diffusion-v1-5-archive/resolve/main/v1-5-pruned-emaonly.safetensors
```

### 2. Check the API is live

```bash
curl http://127.0.0.1:8188/rest/v1/ping
# {"ok": true, "service": "rest_api", "version": "0.1"}

curl http://127.0.0.1:8188/rest/v1/workflows
# {"workflows": ["txt2img_sd15"], "dir": ".../api_workflows"}
```

### 3. Run it

```bash
curl -X POST http://127.0.0.1:8188/rest/v1/execute \
  -H 'Content-Type: application/json' \
  -d '{
        "workflow": "txt2img_sd15",
        "params": {"prompt": "a corgi on the beach", "seed": 42}
      }'
```

Response:

```json
{
  "status": "completed",
  "prompt_id": "b42c68d8-...",
  "images": ["http://127.0.0.1:8188/view?filename=rest_api_00001_.png&subfolder=&type=output"],
  "images_by_var": {"image": ["http://127.0.0.1:8188/view?..."]},
  "texts_by_var": {},
  "node_errors": {}
}
```

Open the URL in a browser — there's your image.

---

## How it works

```
┌─────────────┐   POST /rest/v1/execute   ┌───────────────────────┐
│  Your app   │ ────────────────────────► │  ComfyUI_Rest_API     │
│             │                           │  (custom_node plugin) │
└─────────────┘                           └──────────┬────────────┘
                                                     │
                                    1. Load workflow JSON
                                       (dict | URL | saved name)
                                    2. Apply `$param` markers
                                       (overrides selected fields)
                                    3. Enqueue into ComfyUI's
                                       internal prompt queue
                                    4. Poll history for results
                                    5. Build `/view?...` URLs
                                                     │
                                                     ▼
                                           ┌──────────────────┐
                                           │  ComfyUI engine  │
                                           └──────────────────┘
```

Key idea: **a ComfyUI workflow JSON already contains all widget defaults
(seed, steps, cfg, checkpoint, prompt text, etc.)**. This plugin just
lets you mark a handful of fields as "overridable from the HTTP request"
by putting a `$name` tag in the node's title. Every field not marked
keeps its default. So *the same JSON file* works both as a ComfyUI
workflow and as an API endpoint.

---

## Workflow preparation — the `$` marker syntax

In the ComfyUI web UI, right-click a node → *Title* → edit it to embed
one or more markers, comma-separated. Then `Export (API)` and save the
file to `user/default/api_workflows/<name>.json`.

### Marker grammar

| Marker | Where to put it | Meaning |
|---|---|---|
| `$var` | any node | Request `params.var` is copied to `inputs.var` on this node |
| `$var.field` | any node | Request `params.var` is copied to `inputs.field` |
| `$a.f1,$b.f2` | any node | Multiple markers on one node |
| `$image` | LoadImage / LoadImageMask / VHS_LoadVideo | Request `params.image` is written to `inputs.image`; if it's a URL the plugin downloads it first |
| `$output.name` | SaveImage / SaveVideo / any output node | Products of this node are grouped under `images_by_var.name` in the response |

### Example

Original title: `KSampler`
Becomes: `KSampler $seed.seed,$steps.steps,$cfg.cfg`

Now the HTTP caller can override any subset:

```json
{"params": {"seed": 42, "steps": 12}}   // cfg keeps its widget default
```

Original title: `Positive Prompt`
Becomes: `Positive $prompt.text`

```json
{"params": {"prompt": "a corgi on the beach"}}
```

Original title: `SaveImage`
Becomes: `Save $output.image`

Response will contain:

```json
{"images_by_var": {"image": ["http://.../view?..."]}}
```

### Shortcut: field name defaults to the variable name

`$seed` on a KSampler node is equivalent to `$seed.seed`. Use the short
form when the variable name matches the node's input field name.

### Widget defaults are preserved

Anything you don't override stays as-is. A workflow with 40 nodes and 3
markers is still a valid ComfyUI workflow, and exposes 3 parameters over
HTTP. No code generation, no schema files, no rebuild step.

---

## API reference

Base prefix: **`/rest/v1`**

### `GET /ping`

Health check.

```json
{"ok": true, "service": "rest_api", "version": "0.1"}
```

### `GET /workflows`

List all saved workflows.

```json
{
  "workflows": ["txt2img_sd15", "img2img_controlnet"],
  "dir": "/.../user/default/api_workflows"
}
```

### `POST /save-workflow`

Save a workflow JSON to the user directory.

Request:
```json
{
  "name": "my_flow",
  "workflow": { /* full API-format workflow JSON */ }
}
```

Response:
```json
{"ok": true, "name": "my_flow", "path": "/.../api_workflows/my_flow.json"}
```

### `POST /upload` (multipart/form-data)

Upload one or more files. Form field name must be `file`, `files` or
`image`. Files are saved to `ComfyUI/input/tmp/<uuid>.<ext>`.

Response:
```json
{
  "files": [
    {
      "name": "tmp/3fa85f64....png",
      "original_name": "cat.png",
      "url": "http://127.0.0.1:8188/view?filename=3fa85f64....png&subfolder=tmp&type=input"
    }
  ]
}
```

The returned `name` (e.g. `tmp/3fa85f64....png`) can be used directly as
a `$image` parameter value in `/execute`.

### `POST /execute`

Run a workflow. The single most important endpoint.

Request:
```json
{
  "workflow": "txt2img_sd15",
  "params": {
    "prompt": "a photo of a cat",
    "seed": 42,
    "image": "tmp/abc.png"
  },
  "wait_for_result": true,
  "timeout": 300
}
```

Field reference:

| Field | Type | Default | Description |
|---|---|---|---|
| `workflow` | dict / string | **required** | API-format JSON dict, saved name, or `http(s)://...` URL |
| `params` | object | `{}` | Values for the `$`-marked variables |
| `wait_for_result` | bool | `true` | `true` = sync; `false` = async |
| `timeout` | number | `300` | Seconds before giving up |

**Sync response** (`wait_for_result: true`):

```json
{
  "status": "completed",
  "prompt_id": "b42c68d8-...",
  "images": ["http://.../view?..."],
  "images_by_var": {"image": ["http://.../view?..."]},
  "texts_by_var": {},
  "node_errors": {}
}
```

**Async response** (`wait_for_result: false`):

```json
{
  "task_id": "7de781ed-...",
  "status": "pending",
  "result_url": "http://127.0.0.1:8188/rest/v1/result/7de781ed-..."
}
```

The server also logs the full `result_url` so you can copy it from
stdout.

### `GET /result/{task_id}`

Poll an async task.

- While running:
  ```json
  {"task_id": "...", "status": "pending", "prompt_id": "..."}
  ```
- On success: same shape as the sync response, with `status: "completed"`.
- On failure:
  ```json
  {"task_id": "...", "status": "failed", "error": "..."}
  ```

Tasks are kept in memory only. They disappear on ComfyUI restart.

---

## Input types: text, local files, uploads, URLs

### 1. Text / number / bool

Just put them in `params`:

```json
{"params": {"prompt": "a cat", "seed": 42, "steps": 20}}
```

### 2. Local file already in ComfyUI's `input/` directory

Pass the filename (or `subdir/filename`) as a string:

```json
{"params": {"image": "cat.png"}}
{"params": {"image": "tmp/cat.png"}}
```

This is identical to how ComfyUI's built-in `LoadImage` node references
files.

### 3. Upload a file, then reference it

Step 1 — upload:

```bash
curl -X POST http://127.0.0.1:8188/rest/v1/upload \
     -F "file=@./cat.png"
```

Response:

```json
{"files":[{"name":"tmp/3fa85f64....png", ...}]}
```

Step 2 — pass the returned `name` to `/execute`:

```json
{"params": {"image": "tmp/3fa85f64....png"}}
```

The file now lives under `ComfyUI/input/tmp/` and behaves exactly like
any other local input.

### 4. Remote URL (auto-downloaded)

If a value for `image`, `video`, `audio`, `mask`, or any key ending with
`_image` starts with `http://` or `https://`, the plugin downloads it
into `input/tmp/` first, then substitutes the local path.

```json
{"params": {"image": "https://example.com/cat.png"}}
```

---

## Output types: images, videos, text

All outputs are returned as **HTTP URLs**. The media files live in
`ComfyUI/output/` (or `temp/`) and are served by ComfyUI's built-in
`/view` endpoint.

- **Images / videos / audio**: pulled from the node's `images`, `gifs`,
  `videos`, `audio` output lists.
- **Text**: if an output node exposes a `text` / `string` field in its
  UI output (e.g. `ShowText` custom node), it shows up in
  `texts_by_var`.

Response shape:

```json
{
  "images": ["http://host/view?...", "http://host/view?..."],
  "images_by_var": {
    "main": ["http://host/view?..."],
    "mask": ["http://host/view?..."]
  },
  "texts_by_var": {
    "caption": ["A photo of a corgi."]
  }
}
```

- `images` is the **flat** list of every media URL, in node-visit order.
- `images_by_var` is keyed by the `$output.name` marker. Unmarked output
  nodes use their node id as the key.

---

## Sync vs async

| Mode | When to use | Pros | Cons |
|---|---|---|---|
| **Sync** (`wait_for_result: true`, default) | Fast workflows (< 30s), scripting, notebooks | One round-trip, simplest code | HTTP connection held open the whole time |
| **Async** (`wait_for_result: false`) | Slow workflows, web frontends, long-running jobs | Returns immediately; poll at your own pace | Extra polling logic |

Async polling pattern:

```python
import time, requests
r = requests.post(".../execute", json={..., "wait_for_result": False}).json()
result_url = r["result_url"]
while True:
    r = requests.get(result_url).json()
    if r["status"] in ("completed", "failed"):
        break
    time.sleep(1)
```

---

## Full examples (curl + Python)

### curl — sync text2image

```bash
curl -X POST http://127.0.0.1:8188/rest/v1/execute \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "txt2img_sd15",
    "params": {
      "prompt": "a corgi wearing sunglasses, studio light",
      "negative": "blurry, low quality",
      "seed": 12345,
      "steps": 20,
      "width": 768,
      "height": 512
    }
  }'
```

### curl — upload then image2image

```bash
# 1. upload
FILE_NAME=$(curl -s -X POST http://127.0.0.1:8188/rest/v1/upload \
              -F "file=@./input.png" | jq -r '.files[0].name')

# 2. execute (assuming an img2img workflow named "img2img_sd15" with $image + $prompt)
curl -X POST http://127.0.0.1:8188/rest/v1/execute \
  -H 'Content-Type: application/json' \
  -d "{
    \"workflow\": \"img2img_sd15\",
    \"params\": {\"image\": \"$FILE_NAME\", \"prompt\": \"van gogh style\"}
  }"
```

### Python — async + poll

```python
import time, requests

BASE = "http://127.0.0.1:8188/rest/v1"

r = requests.post(f"{BASE}/execute", json={
    "workflow": "txt2img_sd15",
    "params": {"prompt": "a mountain sunrise", "seed": 7},
    "wait_for_result": False,
}).json()

print("queued:", r["task_id"])
result_url = r["result_url"]

while True:
    r = requests.get(result_url).json()
    if r["status"] == "completed":
        print("images:", r["images"])
        break
    if r["status"] == "failed":
        raise RuntimeError(r["error"])
    time.sleep(1)
```

### Python — upload in one shot

```python
import requests
BASE = "http://127.0.0.1:8188/rest/v1"

# upload
with open("cat.png", "rb") as f:
    up = requests.post(f"{BASE}/upload", files={"file": f}).json()
image_name = up["files"][0]["name"]            # e.g. "tmp/abc.png"

# run
r = requests.post(f"{BASE}/execute", json={
    "workflow": "img2img_sd15",
    "params": {"image": image_name, "prompt": "in the style of Ghibli"},
}).json()
print(r["images"])
```

### Video output with `VHS_VideoCombine`

`VHS_VideoCombine` (from [ComfyUI-VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite))
is the standard node for writing videos. Mark it with `$output.<name>`
exactly like `SaveImage`:

In the ComfyUI web UI, right-click the `VHS_VideoCombine` node and set
its **Title** to:

```
Video Combine $output.video
```

That's the only change. Keep all widget defaults (`frame_rate`,
`format`, `pingpong`, `save_output`, etc.) — the plugin does not
touch them.

**Response shape** after running such a workflow:

```json
{
  "status": "completed",
  "images": [
    "http://127.0.0.1:8188/view?filename=AnimateDiff_00001.mp4&subfolder=&type=output"
  ],
  "images_by_var": {
    "video": [
      "http://127.0.0.1:8188/view?filename=AnimateDiff_00001.mp4&subfolder=&type=output"
    ]
  },
  "texts_by_var": {}
}
```

Notes:

- The flat field is still called `images` (it's a media URL list; the
  name is historical) but the value is a real `.mp4` / `.webm` / `.gif`
  URL you can embed in `<video>` tags directly.
- `VHS_VideoCombine` emits its outputs under the `gifs` key in ComfyUI's
  history — the plugin already handles that, no extra config needed.
- If you mark multiple output nodes, each gets its own key:
  ```
  $output.video     on VHS_VideoCombine
  $output.preview   on SaveImage
  ```
  gives you `images_by_var.video` and `images_by_var.preview`.
- Want to override the frame rate from the request? Add another marker
  to the same node title:
  ```
  Video Combine $output.video,$fps.frame_rate
  ```
  Then call with `{"params": {"fps": 24}}`.

**Minimal curl example** (assuming a saved workflow `txt2video` whose
`VHS_VideoCombine` node is titled `$output.video` and whose prompt node
is titled `$prompt.text`):

```bash
curl -X POST http://127.0.0.1:8188/rest/v1/execute \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "txt2video",
    "params": {"prompt": "a cat surfing a wave, cinematic"},
    "timeout": 900
  }'
```

### Workflow as inline dict (no saved file)

```python
import json, requests
wf = json.load(open("exported_from_comfyui.json"))
r = requests.post("http://127.0.0.1:8188/rest/v1/execute", json={
    "workflow": wf,
    "params": {"prompt": "hello world"},
}).json()
```

### Save a workflow via API

```bash
curl -X POST http://127.0.0.1:8188/rest/v1/save-workflow \
  -H 'Content-Type: application/json' \
  -d @- <<'EOF'
{
  "name": "my_flow",
  "workflow": { "3": {"class_type": "KSampler", "_meta": {"title": "$seed.seed"}, "inputs": {...}}, ... }
}
EOF
```

---

## Testing

A self-contained end-to-end test is included. It hits ping → list →
sync execute → async execute → poll.

Prerequisites:
- ComfyUI is running with this plugin loaded
- `v1-5-pruned-emaonly.safetensors` exists in `models/checkpoints/`
- `txt2img_sd15` workflow exists in `user/default/api_workflows/`
  (copy from `examples/`)

Run:

```bash
python ComfyUI/custom_nodes/ComfyUI_Rest_API/test.py \
       --host http://127.0.0.1:8188
```

Expected tail of output:

```
[3] sync execute txt2img_sd15
 -> 200 { ... "status": "completed", "images": [...] ... }
 sync done in 2.2s
[4] async execute txt2img_sd15
 -> 200 {'task_id': '...', 'status': 'pending', 'result_url': '...'}
[5] poll http://127.0.0.1:8188/rest/v1/result/...
 -> 200 pending
 -> 200 completed
ALL OK
```

---

## FAQ

**Q: Do I need to restart ComfyUI after adding a workflow to `api_workflows/`?**
No. Workflows are read from disk on each request. Restart only when you
update the plugin code itself.

**Q: Where exactly is `user/default/api_workflows/`?**
It's under the ComfyUI user directory. In a standard install that's
`ComfyUI/user/default/api_workflows/`. If you launched ComfyUI with
`--user-directory`, use that path instead.

**Q: Can I use this with non-image workflows (audio, video, LLM)?**
Yes. Any SaveXxx / OutputXxx node that writes files under `output/`
will show up in `images`/`images_by_var` as URLs (the key name is
`images` for historical reasons but it includes videos and audio too).

**Q: Can I stream progress?**
Not in this plugin. Use ComfyUI's existing WebSocket if you need
progress events. This plugin is for "submit → get results" use cases.

**Q: Is it safe to expose to the internet?**
There's no auth, no rate-limit, and `/upload` writes to disk. Put it
behind a reverse proxy with auth if you expose it.

**Q: How do I reset async tasks?**
Restart ComfyUI. The task store is in-memory only by design.

**Q: Multiple concurrent requests?**
Yes. Requests are queued into ComfyUI's normal prompt queue and
processed one at a time by the engine, but HTTP handlers are fully
async and non-blocking.

---

## License

MIT

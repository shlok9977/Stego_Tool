"""
Web front-end for StegoSuite, so the tool can run on Render (gunicorn app:app).

All real work is done by the existing `stego` package. The only code that touches
`stego.api` is the ADAPTER section below. If your function names, argument names
or return types differ, that is the one place to change.
"""
import io
import os
import tempfile

from flask import Flask, render_template_string, request, send_file
from werkzeug.utils import secure_filename

from stego import api

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024  # 15 MB per request

IMAGE_AUDIO_EXT = {".png", ".bmp", ".wav"}  # lossless carriers only


# --------------------------------------------------------------------------
# ADAPTER: adjust these three functions to match stego/api.py
# --------------------------------------------------------------------------
def run_hide(carrier_path, out_path, text, payload_path, password, bits):
    """Hide either `text` or the file at `payload_path` inside the carrier."""
    if payload_path:
        api.hide(carrier_path, out_path, payload_path, is_file=True,
                 password=password or None, bits=bits)
    else:
        api.hide(carrier_path, out_path, text, is_file=False,
                 password=password or None, bits=bits)


def run_reveal(stego_path, out_dir, password):
    """Return ("text", str) or ("file", path_to_extracted_file)."""
    result = api.reveal(stego_path, out_dir, password=password or None)
    # Assumed shape: dict with "is_file" and either "text" or "path".
    if result.get("is_file"):
        return "file", result["path"]
    return "text", result["text"]


def run_capacity(path):
    """Return {bits_per_element: capacity_in_bytes}."""
    return api.get_capacity(path)
# --------------------------------------------------------------------------


def _save_upload(field, workdir, required=True):
    f = request.files.get(field)
    if not f or not f.filename:
        if required:
            raise ValueError("Choose a file to upload.")
        return None
    name = secure_filename(f.filename)
    ext = os.path.splitext(name)[1].lower()
    if field != "payload_file" and ext not in IMAGE_AUDIO_EXT:
        raise ValueError("Use a PNG, BMP or WAV file. JPEG and MP3 destroy hidden data.")
    path = os.path.join(workdir, name)
    f.save(path)
    return path


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>StegoSuite</title>
<style>
  :root{
    --bg:#e8edf1; --panel:#f6f8fa; --ink:#15222c; --muted:#56656f;
    --line:#c3cdd5; --accent:#0d6a6f; --accent-ink:#ffffff; --err:#9b2226;
  }
  @media (prefers-color-scheme: dark){
    :root{ --bg:#101a21; --panel:#17232c; --ink:#e6edf2; --muted:#93a3ae;
           --line:#2b3b47; --accent:#4fc0c4; --accent-ink:#06282a; --err:#ff8b8f; }
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
  main{max-width:720px;margin:0 auto;padding:40px 20px 64px}
  h1{font:600 2rem/1.15 Georgia,"Iowan Old Style",serif;margin:0 0 6px}
  .lede{color:var(--muted);margin:0 0 28px;max-width:56ch}
  section{background:var(--panel);border:1px solid var(--line);border-radius:6px;
          padding:22px;margin:0 0 20px}
  h2{font:600 1.15rem/1.3 Georgia,serif;margin:0 0 14px}
  label{display:block;font-weight:600;margin:14px 0 4px}
  .hint{color:var(--muted);font-weight:400;font-size:.9rem}
  input[type=file],input[type=password],input[type=number],textarea,select{
    width:100%;padding:9px 10px;border:1px solid var(--line);border-radius:4px;
    background:var(--bg);color:var(--ink);font:inherit}
  textarea{min-height:90px;resize:vertical}
  button{margin-top:18px;padding:10px 18px;border:0;border-radius:4px;cursor:pointer;
         background:var(--accent);color:var(--accent-ink);font:600 1rem system-ui}
  button:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible{
    outline:2px solid var(--accent);outline-offset:2px}
  .msg{border-left:4px solid var(--accent);padding:10px 14px;margin:0 0 20px;
       background:var(--panel)}
  .msg.err{border-color:var(--err);color:var(--err)}
  pre{white-space:pre-wrap;word-break:break-word;margin:8px 0 0}
  table{border-collapse:collapse;margin-top:10px}
  td,th{border:1px solid var(--line);padding:6px 12px;text-align:left}
  footer{color:var(--muted);font-size:.9rem;margin-top:28px}
</style>
</head>
<body>
<main>
  <h1>StegoSuite</h1>
  <p class="lede">Hide text or a file inside a PNG, BMP or WAV, and pull it back out.
     Files are processed in memory-backed temp folders and deleted right after.</p>

  {% if error %}<div class="msg err" role="alert">{{ error }}</div>{% endif %}
  {% if text_result is not none %}
    <div class="msg"><strong>Extracted message</strong><pre>{{ text_result }}</pre></div>
  {% endif %}
  {% if capacity %}
    <div class="msg"><strong>Capacity of {{ capacity_name }}</strong>
      <table>
        <tr><th>Bits per channel</th><th>Bytes that fit</th></tr>
        {% for b, n in capacity.items() %}<tr><td>{{ b }}</td><td>{{ n }}</td></tr>{% endfor %}
      </table>
    </div>
  {% endif %}

  <section>
    <h2>Hide data</h2>
    <form method="post" action="/hide" enctype="multipart/form-data">
      <label for="carrier">Carrier file <span class="hint">PNG, BMP or WAV</span></label>
      <input id="carrier" type="file" name="carrier" accept=".png,.bmp,.wav" required>

      <label for="text">Text message</label>
      <textarea id="text" name="text"></textarea>

      <label for="payload_file">Or a file to hide <span class="hint">used instead of the text if chosen</span></label>
      <input id="payload_file" type="file" name="payload_file">

      <label for="bits">Bits per channel <span class="hint">more capacity, easier to detect</span></label>
      <select id="bits" name="bits">
        <option>1</option><option>2</option><option>3</option><option>4</option>
      </select>

      <label for="password_h">Password <span class="hint">optional, enables AES-256 encryption</span></label>
      <input id="password_h" type="password" name="password" autocomplete="new-password">

      <button type="submit">Hide and download</button>
    </form>
  </section>

  <section>
    <h2>Extract data</h2>
    <form method="post" action="/extract" enctype="multipart/form-data">
      <label for="stego">File with hidden data</label>
      <input id="stego" type="file" name="stego" accept=".png,.bmp,.wav" required>

      <label for="password_e">Password <span class="hint">if one was set</span></label>
      <input id="password_e" type="password" name="password" autocomplete="off">

      <button type="submit">Extract</button>
    </form>
  </section>

  <section>
    <h2>Check capacity</h2>
    <form method="post" action="/capacity" enctype="multipart/form-data">
      <label for="cap_file">Carrier file</label>
      <input id="cap_file" type="file" name="carrier" accept=".png,.bmp,.wav" required>
      <button type="submit">Check capacity</button>
    </form>
  </section>

  <footer>For education and authorized security research. Keep outputs as PNG, BMP or WAV;
    converting to JPEG or MP3 destroys the hidden data.</footer>
</main>
</body>
</html>"""


def render(error=None, text_result=None, capacity=None, capacity_name=None, status=200):
    html = render_template_string(
        PAGE, error=error, text_result=text_result,
        capacity=capacity, capacity_name=capacity_name,
    )
    return html, status


@app.get("/")
def index():
    return render()


@app.get("/healthz")
def healthz():
    return "ok"


@app.post("/hide")
def hide_route():
    try:
        bits = int(request.form.get("bits", 1))
        if bits not in (1, 2, 3, 4):
            raise ValueError("Bits per channel must be between 1 and 4.")
        text = request.form.get("text", "")
        password = request.form.get("password", "")
        with tempfile.TemporaryDirectory() as tmp:
            carrier = _save_upload("carrier", tmp)
            payload = _save_upload("payload_file", tmp, required=False)
            if not payload and not text:
                raise ValueError("Enter a message or choose a file to hide.")
            ext = os.path.splitext(carrier)[1].lower()
            out_path = os.path.join(tmp, "stego_output" + ext)
            run_hide(carrier, out_path, text, payload, password, bits)
            with open(out_path, "rb") as fh:
                data = io.BytesIO(fh.read())
        return send_file(data, as_attachment=True, download_name="stego_output" + ext)
    except Exception as exc:  # show a readable message, never a stack trace
        return render(error=f"Could not hide the data: {exc}", status=400)


@app.post("/extract")
def extract_route():
    try:
        password = request.form.get("password", "")
        with tempfile.TemporaryDirectory() as tmp:
            stego_path = _save_upload("stego", tmp)
            out_dir = os.path.join(tmp, "out")
            os.makedirs(out_dir)
            kind, value = run_reveal(stego_path, out_dir, password)
            if kind == "text":
                return render(text_result=value)
            with open(value, "rb") as fh:
                data = io.BytesIO(fh.read())
            name = os.path.basename(value)
        return send_file(data, as_attachment=True, download_name=name)
    except Exception as exc:
        return render(error=f"Could not extract: {exc}", status=400)


@app.post("/capacity")
def capacity_route():
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = _save_upload("carrier", tmp)
            caps = run_capacity(path)
            name = os.path.basename(path)
        return render(capacity=caps, capacity_name=name)
    except Exception as exc:
        return render(error=f"Could not read capacity: {exc}", status=400)


@app.errorhandler(413)
def too_large(_):
    return render(error="That file is too large. The limit is 15 MB.", status=413)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)

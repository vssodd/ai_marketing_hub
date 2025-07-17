import os
import re
import requests
from collections import OrderedDict
from flask import Flask, render_template, request, redirect, url_for, jsonify
from dotenv import load_dotenv
from openai import OpenAI

# 1) Load environment
load_dotenv()
OPENAI_KEY      = os.getenv("OPENAI_API_KEY")
SKETCHFAB_TOKEN = os.getenv("SKETCHFAB_TOKEN")
if not OPENAI_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")

# 2) Instantiate Flask & OpenAI client
app    = Flask(__name__)
client = OpenAI(api_key=OPENAI_KEY)

# 3) Home & generate pages
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/generate")
def generate_page():
    return render_template("generate.html")

# 4) Strategy pipeline
@app.route("/strategy", methods=["POST"])
def strategy():
    product = request.form.get("product", "").strip()
    if not product:
        return redirect(url_for("generate_page"))

    # 4.1) DISCOVERY
    disc_prompt = f"""
You are a market analyst. Research the top competitors, market size, and user trends for “{product}”.
Answer in 3–5 concise bullet points.
"""
    discovery = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": disc_prompt}],
        temperature=0.5,
        max_tokens=300
    ).choices[0].message.content.strip()

    # 4.2) OUTLINE
    outline_prompt = f"""
Based on these bullets:
{discovery}

Create a **10-section outline** for “{product}” with **bold** headings:
1. Executive Summary  
2. Campaign Objectives  
3. Target Audience  
4. Positioning & USP  
5. SWOT Analysis  
6. Marketing Channels & Tactics  
7. Budget Allocation  
8. KPIs & Measurement  
9. Campaign Timeline  
10. Next Steps
"""
    outline = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": outline_prompt}],
        temperature=0.6,
        max_tokens=600
    ).choices[0].message.content.strip()

    # 4.3) DEEP-DIVE
    deep_prompt = f"""
Expand each section of this outline into actionable bullet points, including technical "how-to" examples
(e.g., UTM parameter snippets, tracking-pixel setup, A/B test ideas).

{outline}
"""
    deep_resp = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {
                "role": "system",
                "content": "When you output section titles, ALWAYS wrap them in Markdown bold, e.g. **Executive Summary**."
            },
            {"role": "user", "content": deep_prompt}
        ],
        temperature=0.7,
        max_tokens=2000
    )
    deep = deep_resp.choices[0].message.content.strip()
    app.logger.debug("Deep response:\n" + deep)

    # 4.4) Parse into { heading: [bullets] }
    groups = OrderedDict()
    current = None
    for line in deep.splitlines():
        line = line.strip()
        # 1) Markdown bold headings
        if line.startswith("**") and line.endswith("**"):
            current = line.strip("* ")
            groups[current] = []
            continue
        # 2) Numeric headings (e.g. "1. Executive Summary")
        m = re.match(r"^\d{1,2}\.\s+(.+)$", line)
        if m:
            current = m.group(1).strip()
            groups[current] = []
            continue
        # 3) Bullet items
        if current and (line.startswith("-") or line.startswith("•")):
            groups[current].append(line.lstrip("-• ").strip())

    raw_fallback = deep if not groups else None

    # 4.5) SUMMARY introduction
    summary = client.chat.completions.create(
        model="gpt-4",
        messages=[{
            "role": "user",
            "content": f"Write a 2-sentence introduction summarizing the above strategy for “{product}”."
        }],
        temperature=0.5,
        max_tokens=100
    ).choices[0].message.content.strip()

    # 4.6) Sketchfab lookup
    model_uid = None
    if SKETCHFAB_TOKEN:
        try:
            headers = {"Authorization": f"Bearer {SKETCHFAB_TOKEN}"}
            params  = {"type":"models", "q":product, "sort_by":"relevance", "limit":1}
            r       = requests.get("https://api.sketchfab.com/v3/search", headers=headers, params=params)
            r.raise_for_status()
            results = r.json().get("results", [])
            if results:
                model_uid = results[0]["uid"]
        except Exception:
            pass

    return render_template(
        "result.html",
        product=product,
        summary=summary,
        groups=groups,
        deep_text=raw_fallback,
        model_uid=model_uid
    )

# 5) Live-chat AJAX endpoint
@app.route("/chat", methods=["POST"])
def chat():
    data     = request.get_json() or {}
    product  = data.get("product", "")
    user_msg = data.get("message", "")
    resp = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role":"system", "content":"You are a helpful AI marketing assistant."},
            {"role":"user",   "content":f"Context: strategy for {product}. User asks: {user_msg}"}
        ]
    )
    return jsonify({"message": resp.choices[0].message.content})

# 6) DALL·E image generator
@app.route("/generate-image", methods=["GET","POST"])
def generate_image():
    prompt = request.form.get("prompt","")
    img_url = None
    if prompt:
        img = client.images.generate(model="dall-e-3", prompt=prompt, n=1, size="1024x1024")
        img_url = img.data[0].url
    return render_template("generate_image.html", image_url=img_url, prompt=prompt)

# 7) Launch
if __name__ == "__main__":
    app.run(debug=True)
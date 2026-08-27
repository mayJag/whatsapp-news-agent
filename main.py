import os
import json
import re
import sys
import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

load_dotenv()

GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "claude-omniroute")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
GEMINI_MODEL = "gemini-3.7-flash"
WA_ACCESS_TOKEN = os.environ["WA_ACCESS_TOKEN"]
WA_PHONE_ID = os.environ["WA_PHONE_ID"]
WA_TO = os.environ["WA_TO"]
WA_TEMPLATE_NAME = os.environ["WA_TEMPLATE_NAME"]
WA_TEMPLATE_LANG = os.environ.get("WA_TEMPLATE_LANG", "en_US")

WHATSAPP_API_VERSION = "v25.0"
WHATSAPP_API_URL = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{WA_PHONE_ID}/messages"

RSS_FEEDS = {
    "global": "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
    "india": "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
    "tech": "https://news.google.com/rss/search?q=technology+news&hl=en-US&gl=US&ceid=US:en",
    "sports": "https://news.google.com/rss/search?q=sports+news&hl=en-US&gl=US&ceid=US:en",
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://news.google.com/",
}


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def fetch_rss(url: str, count: int = 5) -> list[dict]:
    resp = requests.get(url, timeout=10, headers=_HEADERS)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    articles = []
    for item in root.findall(".//item")[:count]:
        title = item.findtext("title", "")
        if " - " in title:
            title = title.rsplit(" - ", 1)[0]
        description = strip_html(item.findtext("description", ""))
        articles.append({"title": title, "description": description})
    return articles


def fetch_all_news() -> dict:
    return {k: fetch_rss(v) for k, v in RSS_FEEDS.items()}


SECTION_ORDER = ["global", "india", "tech", "sports"]


def format_with_gemini(news_data: dict) -> dict:
    from google import genai
    from google.genai import types

    system_prompt = (
        "You are a highly concise, professional news editor. "
        "You will receive a JSON object with four keys: global, india, tech, sports. "
        "Each key contains up to 5 articles with title and description fields. "
        "Output ONLY a JSON object with exactly these four keys: global, india, tech, sports. "
        "Each value must be a SINGLE LINE of plain text (no newlines) containing 3 to 4 punchy "
        "story summaries (max 12 words each), separated by ' • '. No URLs, no markdown, no headers "
        "— just the bullet-separated summaries. Omit any story where both title and description are "
        "empty. Each value must stay under 220 characters."
    )
    prompt = f"{system_prompt}\n\n{json.dumps(news_data, ensure_ascii=False)}"

    client = genai.Client(vertexai=True, project=GOOGLE_CLOUD_PROJECT, location=GOOGLE_CLOUD_LOCATION)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
        config=types.GenerateContentConfig(
            temperature=0.3,
            response_mime_type="application/json",
            http_options=types.HttpOptions(timeout=60 * 1000),
        ),
    )
    if not response.text:
        raise RuntimeError(f"Unexpected empty Gemini response: {response}")
    sections = json.loads(response.text)
    return {key: sections.get(key, "") for key in SECTION_ORDER}


def sanitize_template_param(text: str) -> str:
    # WhatsApp template parameters reject newline/tab characters and runs of 4+ spaces.
    text = re.sub(r"[\n\t]+", " • ", text)
    text = re.sub(r" {2,}", " ", text)
    text = text.strip()
    if len(text) > 250:
        text = text[:247] + "..."
    return text


def send_whatsapp_template(sections: dict) -> list[str]:
    parameters = [
        {"type": "text", "text": sanitize_template_param(sections[key])} for key in SECTION_ORDER
    ]

    message_ids = []
    for number in WA_TO.split(","):
        payload = {
            "messaging_product": "whatsapp",
            "to": number.strip(),
            "type": "template",
            "template": {
                "name": WA_TEMPLATE_NAME,
                "language": {"code": WA_TEMPLATE_LANG},
                "components": [
                    {
                        "type": "body",
                        "parameters": parameters,
                    }
                ],
            },
        }
        resp = requests.post(
            WHATSAPP_API_URL,
            headers={
                "Authorization": f"Bearer {WA_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )
        if not resp.ok:
            print(f"WhatsApp API error {resp.status_code}: {resp.text}", file=sys.stderr)
        resp.raise_for_status()
        message_ids.append(resp.json()["messages"][0]["id"])
    return message_ids


def main() -> None:
    print("Fetching news from Google News RSS feeds...")
    news_data = fetch_all_news()
    for category, articles in news_data.items():
        print(f"  {category}: {len(articles)} articles")

    print("Formatting with Gemini...")
    sections = format_with_gemini(news_data)

    print("Sending WhatsApp template message...")
    message_ids = send_whatsapp_template(sections)
    print(f"Sent. Message IDs: {message_ids}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Agent failed: {exc}", file=sys.stderr)
        sys.exit(1)

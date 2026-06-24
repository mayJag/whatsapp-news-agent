import os
import json
import re
import requests
import xml.etree.ElementTree as ET
import functions_framework
from dotenv import load_dotenv
import anthropic
from twilio.rest import Client

load_dotenv()

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_FROM = os.environ["TWILIO_FROM"]
TWILIO_TO = os.environ["TWILIO_TO"]

RSS_FEEDS = {
    "global": "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
    "india": "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
    "tech": "https://news.google.com/rss/search?q=technology+news&hl=en-US&gl=US&ceid=US:en",
    "sports": "https://news.google.com/rss/search?q=sports+news&hl=en-US&gl=US&ceid=US:en",
}

_HEADERS = {"User-Agent": "Mozilla/5.0"}


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


def format_with_claude(news_data: dict) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system_prompt = (
        "You are a highly concise, professional news editor. "
        "You will receive a JSON object with four keys: global, india, tech, sports. "
        "Each key contains up to 5 articles with title and description fields. "
        "Output ONLY the formatted WhatsApp message — no greetings, no sign-offs, no commentary, no URLs. "
        "Structure the output into exactly four blocks in this order:\n"
        "🌍 *Global News*\n"
        "🇮🇳 *Indian News*\n"
        "💻 *Tech News*\n"
        "🏏 *Sports News*\n\n"
        "Under each block, list 4 to 5 stories as:\n"
        "• One punchy sentence summary (max 12 words).\n\n"
        "Omit any story where both title and description are null or empty. "
        "Total output must stay under 1500 characters."
    )

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=900,
        system=system_prompt,
        messages=[{"role": "user", "content": json.dumps(news_data, ensure_ascii=False)}],
    )
    return message.content[0].text


def send_whatsapp(body: str) -> str:
    if len(body) > 1550:
        body = body[:1547] + "..."
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    sids = []
    for number in TWILIO_TO.split(","):
        msg = twilio_client.messages.create(
            from_=TWILIO_FROM,
            body=body,
            to=number.strip(),
        )
        sids.append(msg.sid)
    return ",".join(sids)


@functions_framework.http
def send_morning_news(request):
    try:
        news_data = fetch_all_news()
        formatted = format_with_claude(news_data)
        sid = send_whatsapp(formatted)
        return {"status": "ok", "message_sid": sid}, 200
    except Exception as e:
        return {"status": "error", "detail": str(e)}, 500

import os
import json
import requests
from dotenv import load_dotenv
import anthropic
from twilio.rest import Client

load_dotenv()

NEWS_API_KEY = os.environ["NEWS_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_FROM = os.environ["TWILIO_FROM"]
TWILIO_TO = os.environ["TWILIO_TO"]

NEWS_API_URL = "https://newsapi.org/v2/top-headlines"


def fetch_headlines(params):
    params["apiKey"] = NEWS_API_KEY
    params["pageSize"] = 3
    resp = requests.get(NEWS_API_URL, params=params, timeout=10)
    resp.raise_for_status()
    articles = resp.json().get("articles", [])
    return [
        {"title": a["title"], "description": a.get("description", ""), "url": a["url"]}
        for a in articles
    ]


def fetch_india_headlines():
    for params in [
        {"country": "in"},
        {"sources": "the-times-of-india,ndtv,the-hindu"},
        {"q": "India", "language": "en"},
    ]:
        try:
            articles = fetch_headlines(params)
            if articles:
                return articles
        except Exception:
            continue
    return []


print("[1/3] Fetching news...")
news_data = {
    "global": fetch_headlines({"category": "general"}),
    "india": fetch_india_headlines(),
    "tech": fetch_headlines({"category": "technology"}),
    "sports": fetch_headlines({"category": "sports"}),
}
print(f"  global: {len(news_data['global'])} articles")
print(f"  india:  {len(news_data['india'])} articles")
print(f"  tech:   {len(news_data['tech'])} articles")
print(f"  sports: {len(news_data['sports'])} articles")

print("\n[2/3] Formatting with Claude...")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    system=(
        "You are a highly concise, professional news editor. "
        "You will receive a JSON object with four keys: global, india, tech, sports. "
        "Each key contains up to 3 articles with title, description, and url fields. "
        "Output ONLY the formatted WhatsApp message — no greetings, no sign-offs, no commentary. "
        "Structure the output into exactly four blocks in this order:\n"
        "🌍 *Global News*\n"
        "🇮🇳 *Indian News*\n"
        "💻 *Tech News*\n"
        "🏏 *Sports News*\n\n"
        "Under each block, list each story as:\n"
        "• One punchy sentence summary.\n"
        "  <url>\n\n"
        "Omit any story where both title and description are null or empty."
    ),
    messages=[{"role": "user", "content": json.dumps(news_data, ensure_ascii=False)}],
)
formatted = message.content[0].text

print("\n--- FORMATTED MESSAGE PREVIEW ---")
print(formatted)
print("---------------------------------")

print("\n[3/3] Sending WhatsApp message...")
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
msg = twilio_client.messages.create(
    from_=TWILIO_FROM,
    body=formatted,
    to=TWILIO_TO,
)
print(f"Done! Message SID: {msg.sid}")

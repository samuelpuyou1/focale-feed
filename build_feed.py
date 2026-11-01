#!/usr/bin/env python3
"""Focale — génère docs/cards.json chaque jour à partir de flux RSS publics.

Légal : on n'utilise que le titre et le chapeau publiés en RSS par les médias (jamais l'article
complet ni les images). L'IA reformule les faits en français avec ses propres mots, et chaque carte
cite le média et renvoie vers l'article original.

IA : API Gemini (offre gratuite), clé dans la variable d'environnement GEMINI_API_KEY.
Aucune dépendance : bibliothèque standard Python 3.9+.

Usage :
    python3 build_feed.py              # appelle Gemini et met à jour docs/cards.json
    python3 build_feed.py --dry-run    # sans IA : affiche les articles retenus
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "docs" / "cards.json"
SOURCES = ROOT / "sources.json"

SUBJECTS = {
    "tech": ["IA", "Big Tech", "Startups", "Cybersécurité"],
    "finance": ["Marchés", "Crypto", "Macro", "Fintech", "Startups"],
}
ALL_SUBJECTS = sorted({s for subjects in SUBJECTS.values() for s in subjects})

PER_TOPIC = 6            # nouvelles cartes par thème et par jour
MAX_AGE_HOURS = 36       # fraîcheur des articles retenus
KEEP_DAYS = 7            # historique conservé dans cards.json
MAX_CARDS = 80
EXCERPT_CHARS = 600
USER_AGENT = "FocaleFeed/1.0 (+https://github.com/focale-feed)"

PREFERRED_MODELS = [m for m in os.environ.get("GEMINI_MODELS", "gemini-2.5-flash,gemini-2.5-flash-lite").split(",") if m]
API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_URL = API_ROOT + "/models/{model}:generateContent"
STATUS = ROOT / "docs" / "status.json"
MODELS: list[str] = []      # rempli par discover_models()
ERRORS: list[str] = []      # résumé publié dans docs/status.json (sans la clé)
DELAY_SECONDS = float(os.environ.get("GEMINI_DELAY", "7"))  # reste sous la limite gratuite par minute


# ---------------------------------------------------------------- RSS

def fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def clean(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    # Formules de fin de chapeau du type « L'article X est apparu en premier sur Y ».
    text = re.sub(r"(The post|L[’']article) .*? (appeared first|est apparu en premier) .*$", "", text).strip()
    return text


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_feed(data: bytes) -> list[dict]:
    """Lit RSS 2.0 et Atom. Retourne [{title, link, excerpt, published}]."""
    root = ET.fromstring(data)
    items = []
    for node in root.iter():
        if local(node.tag) not in ("item", "entry"):
            continue
        fields: dict[str, str] = {}
        for child in node:
            name = local(child.tag)
            if name == "link":
                href = child.get("href")
                if href and child.get("rel", "alternate") == "alternate":
                    fields.setdefault("link", href)
                elif child.text:
                    fields.setdefault("link", child.text.strip())
            elif name in ("title", "description", "summary", "pubDate", "published", "updated", "date"):
                fields.setdefault(name, "".join(child.itertext()))
        link = fields.get("link", "").strip()
        title = clean(fields.get("title"))
        if not link or not title:
            continue
        items.append({
            "title": title,
            "link": link,
            "excerpt": clean(fields.get("description") or fields.get("summary"))[:EXCERPT_CHARS],
            "published": parse_date(fields.get("pubDate") or fields.get("published") or fields.get("date") or fields.get("updated")),
        })
    return items


# Bons plans, guides d'achat, divertissement : hors sujet pour Focale.
OFF_TOPIC = re.compile(
    r"black friday|bon plan|bons plans|promo|soldes|prix cass|meilleur(e)?s? (offres?|smartphones?|tv|forfaits?)|"
    r"code promo|test du|test de la|\bdeal|\bdeals\b|à voir en|séries?\b|films?\b|netflix|prime video|disney\+|"
    r"seulement [0-9]+ ?€|à [0-9]+ ?€|horoscope|recette|quiz|jeu concours|wordle|best .* deals|how to watch|gift guide",
    re.IGNORECASE)


def is_relevant(title: str) -> bool:
    return not OFF_TOPIC.search(title)


def card_id(link: str) -> str:
    return "rss-" + hashlib.sha1(link.encode("utf-8")).hexdigest()[:12]


def collect(sources: list[dict], known_ids: set[str], now: datetime) -> dict[str, list[dict]]:
    """Articles récents et inédits, par thème, en alternant les sources."""
    cutoff = now - timedelta(hours=MAX_AGE_HOURS)
    per_source: dict[str, list[dict]] = {}
    for source in sources:
        try:
            items = parse_feed(fetch(source["url"]))
        except Exception as error:  # un flux en panne ne bloque pas les autres
            print(f"  ! {source['name']}: {error}", file=sys.stderr)
            continue
        fresh = []
        for item in items:
            if item["published"] and item["published"] < cutoff:
                continue
            if len(item["excerpt"]) < 60:  # chapeau trop maigre pour en tirer une carte fiable
                continue
            if not is_relevant(item["title"]):
                continue
            cid = card_id(item["link"])
            if cid in known_ids:
                continue
            item.update(id=cid, source=source["name"], topic=source["topic"],
                        published=item["published"] or now)
            fresh.append(item)
        fresh.sort(key=lambda i: i["published"], reverse=True)
        per_source[source["name"]] = fresh
        print(f"  {source['name']}: {len(items)} articles, {len(fresh)} retenus")

    by_topic: dict[str, list[dict]] = {"tech": [], "finance": []}
    for topic in by_topic:
        queues = [q for s, q in per_source.items() if q and q[0]["topic"] == topic]
        # Tourniquet : un article de chaque source à tour de rôle.
        while queues:
            for queue in list(queues):
                by_topic[topic].append(queue.pop(0))
                if not queue:
                    queues.remove(queue)
    return by_topic


# ---------------------------------------------------------------- IA

PROMPT = """Tu es rédacteur pour Focale, une app française qui résume l'actualité tech et finance en une minute.
À partir UNIQUEMENT de l'extrait ci-dessous, écris une carte en français, avec tes propres mots (ne recopie aucune phrase de l'extrait).
Règles :
- N'invente aucun fait, chiffre ou nom absent de l'extrait. Ton neutre, tutoiement interdit, pas d'emoji.
- "title" : 70 caractères maximum, informatif, sans point final.
- "fact" : une phrase qui dit ce qui s'est passé (« Le fait »).
- "whyItMatters" : 2 phrases qui expliquent l'enjeu pour un lecteur non spécialiste (« Pourquoi ça compte »).
- "subject" : un seul parmi {subjects}.
- "quiz" : une question qui vérifie la compréhension de la carte, 3 choix courts et plausibles dont UN seul juste ;
  "answer" = le texte exact du bon choix ; "explanation" = une phrase.
- Réponds {{"skip": true}} si l'extrait est trop vague pour une carte fiable, OU si le sujet n'est pas une vraie actualité
  {topic_label} utile (politique pure, faits divers, sport, divertissement, conseils d'achat, promotion, publi-rédactionnel).
Réponds uniquement en JSON avec les clés : title, fact, whyItMatters, subject, quiz {{question, choices, answer, explanation}}.

Média : {source}
Titre : {title}
Extrait : {excerpt}"""


class GeminiError(Exception):
    pass


class QuotaExhausted(GeminiError):
    """Quota gratuit épuisé ou indisponible : inutile d'insister aujourd'hui."""


def note(message: str) -> None:
    message = re.sub(r"key=[^&\s]+", "key=***", message)[:400]
    print(f"  ! {message}", file=sys.stderr)
    if len(ERRORS) < 12:
        ERRORS.append(message)


def discover_models(api_key: str) -> list[str]:
    """Modèles Flash disponibles pour cette clé, préférés d'abord."""
    req = urllib.request.Request(API_ROOT + "/models?pageSize=200", headers={"x-goog-api-key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as error:
        note(f"liste des modèles : HTTP {error.code} {error.read()[:300]!r}")
        return PREFERRED_MODELS
    except Exception as error:
        note(f"liste des modèles : {error}")
        return PREFERRED_MODELS
    available = [m["name"].split("/", 1)[-1] for m in payload.get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
    flash = [m for m in available if "flash" in m and not any(x in m for x in ("image", "tts", "live", "audio", "exp", "thinking"))]
    ordered = [m for m in PREFERRED_MODELS if m in flash]
    ordered += sorted((m for m in flash if m not in ordered and "preview" not in m), reverse=True)
    print(f"  Modèles Flash disponibles : {', '.join(ordered[:6]) or 'aucun'}")
    return ordered[:4] or PREFERRED_MODELS


def call_gemini(prompt: str, api_key: str) -> dict:
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4},
    }).encode("utf-8")
    last_error: Exception | None = None
    for model in MODELS:
        for attempt in range(3):
            req = urllib.request.Request(
                GEMINI_URL.format(model=model), data=body, method="POST",
                headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    payload = json.loads(resp.read())
                text = payload["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text)
            except urllib.error.HTTPError as error:
                detail = error.read()[:400].decode("utf-8", "replace")
                last_error = GeminiError(f"{model}: HTTP {error.code} {detail}")
                if error.code == 429:
                    # Quota du jour épuisé ou offre gratuite indisponible : on passe au modèle suivant.
                    if "PerDay" in detail or "limit: 0" in detail or "free_tier" in detail.lower():
                        break
                    time.sleep(20 * (attempt + 1))  # quota par minute : on attend puis on réessaie
                    continue
                if error.code in (400, 401, 403):
                    raise QuotaExhausted(str(last_error))  # clé invalide ou refusée : inutile d'insister
                break                          # modèle indisponible : modèle suivant
            except (KeyError, IndexError, json.JSONDecodeError, urllib.error.URLError, TimeoutError) as error:
                last_error = GeminiError(f"{model}: {error}")
                time.sleep(3)
    if last_error and "HTTP 429" in str(last_error):
        raise QuotaExhausted(str(last_error))
    raise last_error or GeminiError("aucun modèle disponible")


def validate(raw: dict, item: dict, rng: random.Random) -> dict | None:
    """Vérifie la réponse de l'IA et produit une carte au format de l'app. None si invalide."""
    if not isinstance(raw, dict) or raw.get("skip"):
        return None
    try:
        title = str(raw["title"]).strip().rstrip(".")
        fact = str(raw["fact"]).strip()
        why = str(raw["whyItMatters"]).strip()
        subject = str(raw["subject"]).strip()
        quiz = raw["quiz"]
        question = str(quiz["question"]).strip()
        choices = [str(c).strip() for c in quiz["choices"]]
        answer = str(quiz["answer"]).strip()
        explanation = str(quiz["explanation"]).strip()
    except (KeyError, TypeError):
        return None

    if not (8 <= len(title) <= 90 and 20 <= len(fact) <= 320 and 30 <= len(why) <= 500):
        return None
    if subject not in ALL_SUBJECTS or not question or not explanation:
        return None
    choices = list(dict.fromkeys(c for c in choices if c))
    if not 3 <= len(choices) <= 4 or answer not in choices or any(len(c) > 90 for c in choices):
        return None

    rng.shuffle(choices)  # la bonne réponse n'est pas toujours au même endroit
    return {
        "id": item["id"],
        "title": title[:90],
        "topic": item["topic"],
        "subject": subject,
        "fact": fact,
        "whyItMatters": why,
        "summary": f"{fact} {why}",
        "source": item["source"],
        "sourceURL": item["link"],
        "publishedAt": item["published"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quiz": {
            "question": question,
            "choices": choices,
            "answerIndex": choices.index(answer),
            "explanation": explanation,
        },
    }


# ---------------------------------------------------------------- Fusion

def load_existing() -> list[dict]:
    if OUTPUT.exists():
        try:
            return json.loads(OUTPUT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def merge(new_cards: list[dict], existing: list[dict], now: datetime) -> list[dict]:
    cutoff = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    seen: set[str] = set()
    cards = []
    for card in new_cards + existing:
        if card["id"] in seen or card.get("publishedAt", "") < cutoff:
            continue
        seen.add(card["id"])
        cards.append(card)
    cards.sort(key=lambda c: c["publishedAt"], reverse=True)
    return cards[:MAX_CARDS]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="sans IA : liste les articles retenus")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    existing = load_existing()
    print(f"Flux RSS ({len(sources)} sources), {len(existing)} cartes déjà publiées")
    by_topic = collect(sources, {c["id"] for c in existing}, now)

    if args.dry_run:
        for topic, items in by_topic.items():
            print(f"\n[{topic}] {len(items)} candidats")
            for item in items[:PER_TOPIC]:
                print(f"  - {item['source']}: {item['title']}")
        return 0

    api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        note("GEMINI_API_KEY manquante : ajoute le secret dans Settings › Secrets and variables › Actions")
        STATUS.parent.mkdir(parents=True, exist_ok=True)
        STATUS.write_text(json.dumps({"ranAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "errors": ERRORS},
                                     ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 1

    MODELS[:] = discover_models(api_key)
    rng = random.Random(now.strftime("%Y%m%d"))
    new_cards: list[dict] = []
    failures = 0
    stop = False
    for topic, items in by_topic.items():
        made = 0
        for item in items:
            if made >= PER_TOPIC or stop:
                break
            prompt = PROMPT.format(subjects=", ".join(SUBJECTS[topic]), source=item["source"],
                                   topic_label="tech" if topic == "tech" else "économie, finance ou marchés",
                                   title=item["title"], excerpt=item["excerpt"])
            try:
                raw = call_gemini(prompt, api_key)
                card = validate(raw, item, rng)
                failures = 0
                if card is None and not (isinstance(raw, dict) and raw.get("skip")):
                    note(f"réponse invalide ({item['source']}) : {json.dumps(raw, ensure_ascii=False)[:200]}")
            except QuotaExhausted as error:
                note(f"arrêt : {error}")
                stop = True
                card = None
            except GeminiError as error:
                note(f"{item['source']} — {error}")
                card = None
                failures += 1
                if failures >= 4:  # erreurs en série : on s'arrête pour aujourd'hui
                    stop = True
            time.sleep(DELAY_SECONDS)
            if card:
                new_cards.append(card)
                made += 1
                print(f"  + [{topic}] {card['title']}")
            else:
                print(f"  - ignoré : {item['title'][:70]}")

    cards = merge(new_cards, existing, now)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(cards, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(json.dumps({
        "ranAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "models": MODELS, "newCards": len(new_cards),
        "totalCards": len(cards), "candidates": {t: len(i) for t, i in by_topic.items()}, "errors": ERRORS,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{len(new_cards)} nouvelles cartes, {len(cards)} au total → {OUTPUT.relative_to(ROOT)}")
    # Échec seulement si rien n'a pu être produit alors qu'il y avait des candidats.
    return 0 if new_cards or not any(by_topic.values()) else 1


if __name__ == "__main__":
    sys.exit(main())

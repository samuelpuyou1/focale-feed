"""Tests sans réseau : python3 -m unittest discover -s tests"""
import random
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_feed as bf  # noqa: E402

ITEM = {"id": "rss-abc", "topic": "finance", "source": "La Tribune", "link": "https://exemple.fr/a",
        "published": datetime(2026, 11, 1, 6, tzinfo=timezone.utc)}
RAW = {
    "title": "La BCE maintient ses taux",
    "fact": "La Banque centrale européenne laisse ses taux inchangés ce jeudi.",
    "whyItMatters": "Le coût du crédit ne bouge pas pour l'instant. Les marchés attendent une baisse en mars.",
    "subject": "Macro",
    "quiz": {"question": "Que décide la BCE ?", "choices": ["Elle baisse ses taux", "Elle maintient ses taux", "Elle les monte"],
             "answer": "Elle maintient ses taux", "explanation": "Les taux restent au même niveau."},
}

RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Titre A</title><link>https://exemple.fr/a</link><description>&lt;p&gt;Un chapeau &amp;amp; du texte.&lt;/p&gt;</description>
<pubDate>Sun, 01 Nov 2026 06:00:00 +0100</pubDate></item></channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Titre B</title>
<link rel="alternate" href="https://exemple.fr/b"/><summary>Resume</summary><updated>2026-11-01T05:00:00Z</updated></entry></feed>"""


class BuildFeedTests(unittest.TestCase):
    def test_valid_card_keeps_correct_answer(self):
        card = bf.validate(RAW, ITEM, random.Random(1))
        self.assertIsNotNone(card)
        self.assertEqual(card["quiz"]["choices"][card["quiz"]["answerIndex"]], "Elle maintient ses taux")
        self.assertEqual(card["sourceURL"], "https://exemple.fr/a")
        self.assertEqual(card["publishedAt"], "2026-11-01T06:00:00Z")

    def test_rejects_unknown_subject_and_bad_answer(self):
        self.assertIsNone(bf.validate({**RAW, "subject": "Sport"}, ITEM, random.Random(1)))
        bad = {**RAW, "quiz": {**RAW["quiz"], "answer": "Autre"}}
        self.assertIsNone(bf.validate(bad, ITEM, random.Random(1)))
        self.assertIsNone(bf.validate({"skip": True}, ITEM, random.Random(1)))

    def test_parses_rss_and_atom(self):
        rss = bf.parse_feed(RSS)[0]
        self.assertEqual(rss["link"], "https://exemple.fr/a")
        self.assertEqual(rss["excerpt"], "Un chapeau & du texte.")
        self.assertEqual(rss["published"], datetime(2026, 11, 1, 5, tzinfo=timezone.utc))
        atom = bf.parse_feed(ATOM)[0]
        self.assertEqual(atom["link"], "https://exemple.fr/b")

    def test_filters_promotions(self):
        self.assertFalse(bf.is_relevant("Black Friday : les meilleures offres TV"))
        self.assertFalse(bf.is_relevant("Netflix : les séries à voir en novembre"))
        self.assertTrue(bf.is_relevant("La BCE maintient ses taux directeurs"))

    def test_merge_dedupes_and_drops_old(self):
        now = datetime(2026, 11, 1, tzinfo=timezone.utc)
        old = {"id": "old", "publishedAt": (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")}
        a = {"id": "a", "publishedAt": "2026-10-31T10:00:00Z"}
        merged = bf.merge([a], [a, old], now)
        self.assertEqual([c["id"] for c in merged], ["a"])


if __name__ == "__main__":
    unittest.main()


class BatchTests(unittest.TestCase):
    def test_batch_entries_maps_numbers(self):
        raw = {"cards": [{"i": 2, **RAW}, {"i": 1, "skip": True}, {"i": 9, **RAW}, {"i": "x"}]}
        entries = bf.batch_entries(raw, 3)
        self.assertEqual(set(entries), {1, 2})
        self.assertTrue(entries[1]["skip"])

    def test_prompt_numbers_articles(self):
        prompt = bf.batch_prompt("finance", [ITEM | {"title": "A", "excerpt": "x"}, ITEM | {"title": "B", "excerpt": "y"}])
        self.assertIn("[1] Média : La Tribune", prompt)
        self.assertIn("[2]", prompt)
        self.assertIn("Macro", prompt)


class DedupeTests(unittest.TestCase):
    def card(self, title, fact, date="2026-11-01T08:00:00Z"):
        return {"id": title, "title": title, "fact": fact, "publishedAt": date}

    def test_same_story_across_sources(self):
        a = self.card("Le FBI implique la Corée du Nord dans un piratage de Binance",
                      "Le FBI attribue à la Corée du Nord le vol de fonds sur Binance.")
        b = self.card("Le FBI impute à la Corée du Nord un piratage record de Binance",
                      "Selon le FBI, des pirates nord-coréens ont volé des fonds à Binance.")
        c = self.card("Mistral Large 4 renforce la cybersécurité française",
                      "Mistral dévoile un modèle destiné aux équipes de sécurité.")
        self.assertTrue(bf.same_story(a, b))
        self.assertFalse(bf.same_story(a, c))
        b["publishedAt"] = "2026-11-01T09:00:00Z"
        self.assertEqual([x["id"] for x in bf.dedupe([b, a, c])], [a["id"], c["id"]])

    def test_rejects_unaccented_french(self):
        raw = {**RAW, "fact": "Les rendements locatifs sont eleves dans certaines villes francaises cette annee.",
               "whyItMatters": "Les investisseurs peuvent viser ces marches. Le choix de la ville reste decisif pour la rentabilite.",
               "title": "Rendements locatifs eleves"}
        self.assertIsNone(bf.validate(raw, ITEM, random.Random(1)))

    def test_prompt_lists_covered_topics(self):
        prompt = bf.batch_prompt("tech", [ITEM | {"title": "A", "excerpt": "x"}], ["Piratage de Binance"])
        self.assertIn("- Piratage de Binance", prompt)


class ReviewTests(unittest.TestCase):
    def test_review_parses_numbers_and_ignores_errors(self):
        new = [{"title": f"T{i}", "fact": "f"} for i in range(3)]
        original = bf.call_gemini
        try:
            bf.call_gemini = lambda prompt, key: {"duplicates": [2, "N3", 9, "x"]}
            self.assertEqual(bf.review_duplicates(new, [], "k"), {1, 2})
            def boom(prompt, key):
                raise bf.GeminiError("panne")
            bf.call_gemini = boom
            self.assertEqual(bf.review_duplicates(new, [], "k"), set())
        finally:
            bf.call_gemini = original


class TranslationTests(unittest.TestCase):
    CARD = {"id": "x", "title": "La BCE maintient ses taux", "fact": "f", "whyItMatters": "w",
            "quiz": {"question": "q", "choices": ["a", "b", "c"], "answerIndex": 1, "explanation": "e"}}
    EN = {"title": "The ECB holds rates.", "fact": "F", "whyItMatters": "W",
          "quiz": {"question": "Q", "choices": ["A", "B", "C"], "explanation": "E"}}

    def test_valid_translation_keeps_choice_count(self):
        out = bf.valid_translation(self.EN, self.CARD)
        self.assertEqual(out["title"], "The ECB holds rates")
        bad = {**self.EN, "quiz": {**self.EN["quiz"], "choices": ["A", "B"]}}
        self.assertIsNone(bf.valid_translation(bad, self.CARD))
        self.assertIsNone(bf.valid_translation({"title": "x"}, self.CARD))

    def test_translate_cards_fills_every_language(self):
        cards = [dict(self.CARD, id=str(i)) for i in range(3)]
        original, delay = bf.call_gemini, bf.DELAY_SECONDS
        try:
            bf.DELAY_SECONDS = 0
            bf.call_gemini = lambda prompt, key: {"cards": [{"i": n, **self.EN} for n in range(1, 4)]}
            done = bf.translate_cards(cards, "k")
        finally:
            bf.call_gemini, bf.DELAY_SECONDS = original, delay
        self.assertEqual(done, {"en": 3, "es": 3, "hi": 3, "zh": 3})
        self.assertEqual(set(cards[0]["translations"]), {"en", "es", "hi", "zh"})
        self.assertEqual(cards[2]["translations"]["zh"]["quiz"]["choices"], ["A", "B", "C"])



class RegionAndQualityTests(unittest.TestCase):
    def test_card_carries_source_region(self):
        card = bf.validate(RAW, {**ITEM, "region": "in"}, random.Random(1))
        self.assertEqual(card["region"], "in")
        self.assertEqual(bf.validate(RAW, ITEM, random.Random(1))["region"], "fr", "Sans région : France")

    def test_pick_batch_prefers_regions_under_quota(self):
        queue = [{"id": f"fr{i}", "region": "fr"} for i in range(10)] + [{"id": "es1", "region": "es"}]
        batch, rest = bf.pick_batch(queue, {"fr": bf.REGION_QUOTA["fr"], "es": 0}, 4)
        self.assertEqual([i["id"] for i in batch], ["es1"], "La France a déjà son quota : place à l'Espagne")
        self.assertEqual(len(rest), 10)
        full = {r: q for r, q in bf.REGION_QUOTA.items()}
        batch, rest = bf.pick_batch(queue, full, 4)
        self.assertEqual(len(batch), 4, "Tous les quotas remplis : on complète quand même")

    def test_quality_review_fixes_rejects_and_survives_errors(self):
        card = bf.validate(RAW, ITEM, random.Random(1))
        other = dict(card, id="b", title="Une autre carte de la BCE")
        original = bf.call_gemini
        try:
            bf.call_gemini = lambda prompt, key: {"cards": [
                {"i": 1, "fact": "La Banque centrale européenne a laissé ses taux inchangés jeudi."},
                {"i": 2, "reject": True}]}
            kept, fixed, rejected = bf.review_quality([card, other], {}, "k")
            self.assertEqual((len(kept), fixed, rejected), (1, 1, 1))
            self.assertTrue(kept[0]["summary"].startswith("La Banque centrale européenne a laissé"))
            bf.call_gemini = lambda prompt, key: {"cards": [{"i": 1, "subject": "Sport"}]}
            kept, fixed, _ = bf.review_quality([card], {}, "k")
            self.assertEqual((kept[0]["subject"], fixed), ("Macro", 0), "Correction invalide ignorée")
            def boom(prompt, key):
                raise bf.GeminiError("panne")
            bf.call_gemini = boom
            self.assertEqual(bf.review_quality([card], {}, "k")[0], [card])
        finally:
            bf.call_gemini = original


class GlossaryTests(unittest.TestCase):
    def test_terms_must_appear_in_text(self):
        raw = [{"term": "taux directeur", "definition": "Taux auquel la banque centrale prête aux banques."},
               {"term": "inventé", "definition": "Ce terme n'est pas dans le texte de la carte."},
               {"term": "BCE", "definition": "x"}]
        terms = bf.clean_terms(raw, "La BCE baisse son taux directeur.", "Le crédit devient moins cher.")
        self.assertEqual([t["term"] for t in terms], ["taux directeur"])

    def test_at_most_two_terms_and_bad_input(self):
        raw = [{"term": w, "definition": "Une définition assez longue."} for w in ("alpha", "beta", "gamma")]
        self.assertEqual(len(bf.clean_terms(raw, "alpha beta gamma")), 2)
        self.assertEqual(bf.clean_terms("pas une liste", "texte"), [])

    def test_translation_drops_missing_terms_but_stays_valid(self):
        card = {"quiz": {"choices": ["a", "b", "c"]}}
        raw = {"title": "ECB cuts rates", "fact": "The ECB cut its key rate.", "whyItMatters": "Loans get cheaper.",
               "quiz": {"question": "Who?", "choices": ["a", "b", "c"], "explanation": "The ECB."},
               "terms": [{"term": "key rate", "definition": "The rate at which the central bank lends."},
                         {"term": "taux directeur", "definition": "Non traduit, absent du texte anglais."}]}
        out = bf.valid_translation(raw, card)
        self.assertIsNotNone(out)
        self.assertEqual([t["term"] for t in out["terms"]], ["key rate"])


class QuotaDiagnosticTests(unittest.TestCase):
    def test_quota_detail_names_metric_and_limit(self):
        detail = ('{"error": {"code": 429, "message": "You exceeded your current quota. \\n* Quota exceeded for metric: '
                  'generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-2.5-flash", '
                  '"details": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}}')
        text = bf.quota_detail(detail)
        self.assertIn("generate_content_free_tier_requests", text)
        self.assertIn("GenerateRequestsPerDayPerProjectPerModel-FreeTier", text)
        self.assertIn("limite 20", text)


class TopicAndSourceTests(unittest.TestCase):
    def test_topic_follows_subject(self):
        self.assertEqual(bf.topic_for("Macro", "tech"), "finance")
        self.assertEqual(bf.topic_for("Cybersécurité", "finance"), "tech")
        self.assertEqual(bf.topic_for("Startups", "finance"), "finance", "Sujet commun : thème de la source")
        self.assertEqual(bf.topic_for("Startups", "tech"), "tech")

    def test_chinese_sources_have_latin_display_names(self):
        import json
        sources = json.loads(bf.SOURCES.read_text(encoding="utf-8"))
        for source in sources:
            name = source.get("display", source["name"])
            self.assertTrue(all(ord(ch) < 0x2E80 for ch in name), f"nom illisible hors de Chine : {name}")


class DeadModelTests(unittest.TestCase):
    def test_retired_model_is_skipped_for_the_rest_of_the_run(self):
        import io, urllib.error
        calls = []

        def fake_urlopen(req, timeout=0):
            model = req.full_url.split("/models/")[1].split(":")[0]
            calls.append(model)
            if model == "old":
                raise urllib.error.HTTPError(req.full_url, 404, "gone", {}, io.BytesIO(b'{"error":{"message":"no longer available"}}'))
            body = b'{"candidates":[{"content":{"parts":[{"text":"{\\"ok\\": true}"}]}}]}'
            return io.BytesIO(body)

        class Ctx(io.BytesIO):
            pass

        original, saved_models = bf.urllib.request.urlopen, list(bf.MODELS)
        try:
            bf.urllib.request.urlopen = lambda req, timeout=0: _Wrap(fake_urlopen(req, timeout))
            bf.MODELS[:] = ["old", "new"]
            bf.DEAD_MODELS.clear()
            self.assertEqual(bf.call_gemini("p", "k"), {"ok": True})
            self.assertEqual(bf.call_gemini("p", "k"), {"ok": True})
            self.assertEqual(calls, ["old", "new", "new"], "Le modèle retiré n'est appelé qu'une fois")
        finally:
            bf.urllib.request.urlopen = original
            bf.MODELS[:] = saved_models
            bf.DEAD_MODELS.clear()


class _Wrap:
    def __init__(self, inner):
        self.inner = inner

    def __enter__(self):
        return self.inner

    def __exit__(self, *args):
        return False


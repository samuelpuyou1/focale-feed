# focale-feed

Les actus quotidiennes de l'app **Focale** : chaque matin, une GitHub Action lit des flux RSS publics,
fait réécrire chaque actu en français par l'API Gemini (offre gratuite) avec un quiz, et publie
`docs/cards.json`, que l'app télécharge.

- **Sources** : `sources.json` (nom affiché, thème `tech`/`finance`, région `fr`/`en`/`es`/`in`/`cn`, adresse du flux). Ajoute ou retire une ligne. Quotas par région : `REGION_QUOTA` dans `build_feed.py`. État juridique : `SOURCES-LEGAL.md`.
- **Relancer à la main** : onglet *Actions* › *Daily feed* › *Run workflow*.
- **Clé Gemini** : *Settings* › *Secrets and variables* › *Actions* › secret `GEMINI_API_KEY`.
- **Tester en local** : `python3 build_feed.py --dry-run` (sans IA), `python3 -m unittest discover -s tests`.

Respect des médias : seuls le titre et le chapeau publiés en RSS sont utilisés, jamais l'article complet
ni les images ; les faits sont reformulés et chaque carte cite le média avec un lien vers l'article original.
Pour retirer une source, supprime sa ligne dans `sources.json`.

## Langues
Chaque carte est écrite en français puis traduite en anglais, espagnol, hindi et chinois simplifié (`translations`).
Les cartes déjà publiées sans traduction sont rattrapées aux lancements suivants (24 requêtes de traduction au plus par lancement).

# Sources RSS : conditions d'utilisation

Vérifié le 3 novembre 2026. Ce document n'est pas un avis juridique.

Focale reprend le titre et le chapeau du flux, **reformule** les faits avec l'IA, et cite le média avec un lien vers l'article. Le point sensible n'est donc pas l'affichage : c'est la **réécriture** et l'usage dans une app **commerciale**.

## Retirées
| Média | Raison |
|---|---|
| TechCrunch | Ses conditions RSS n'autorisent que l'affichage du contenu tel quel, avec attribution. Elles interdisent de le modifier ou de le réécrire. ([conditions](https://techcrunch.com/rss-terms-of-use)) |
| MarketWatch | Conditions de Dow Jones : le contenu des flux RSS ne peut pas être utilisé dans un produit ou un service commercial sans accord écrit. |

## Ajoutée
| Média | Raison |
|---|---|
| Tech Xplore | Flux fournis « at no charge for both personal and commercial use ». ([page des flux](https://techxplore.com/feeds/)) |

## Institutions publiques (ajoutées le 4 novembre 2026)
| Source | Région | Conditions |
|---|---|---|
| BCE | fr | Réutilisation libre, source citée, sans dénaturer le contenu ([avertissement juridique](https://www.ecb.europa.eu/home/disclaimer/html/index.en.html)) |
| INSEE | fr | Licence Ouverte Etalab : réutilisation libre, y compris commerciale, avec mention de la source |
| AMF, CNIL | fr | Sites publics français ; à confirmer sur leurs mentions légales (Licence Ouverte le plus souvent) |
| Federal Reserve | en | Publications du gouvernement américain, en principe libres de droits |
| RBI | in | Reproduction autorisée avec mention de la source (notices de publications de la RBI) |
| Tech Xplore Business | en | Même réseau que Tech Xplore : usage personnel et commercial autorisé |

Ces sources sont précieuses mais publient peu d'actus « grand public » : l'IA en écarte beaucoup.

## Médias régionaux ajoutés (à faire autoriser avant l'App Store)
Aucune condition RSS publique trouvée : même statut que les médias de la section suivante.
- Espagne : Xataka, Genbeta, Hipertextual, Expansión, El País Economía.
- Inde : Inc42, YourStory, ET Tech.
- Chine : IT之家, cnBeta, 少数派, 华尔街见闻.

## Écartées
- **Mint** : les conditions du groupe Hindustan Times réservent les contenus, flux RSS compris, à un usage personnel et non commercial.
- **PIB** (Inde) et **Business Standard** : ils refusent l'accès au robot (erreur 403).
- **Banque de France, Banco de España, CNMV, El Economista, Gadgets 360, Caixin** : flux inaccessibles (403 ou 404).

## Sans conditions RSS publiques trouvées
The Verge (Vox Media), Ars Technica (Condé Nast), Engadget (Yahoo), CNBC, Cointelegraph, Le Monde, Le Figaro, La Tribune, BFM Business, Challenges, Presse-citron, Numerama, Frandroid, 01net, Journal du Geek, Maddyness.

Pour ces médias, il n'y a ni interdiction ni autorisation explicite. Beaucoup de médias comparables réservent leurs flux à un « usage personnel, non commercial », comme CNN, NBC News ou Brut. Vox Media demande une licence pour tout usage commercial de ses contenus.

## Avant une publication sur l'App Store
1. **Écrire aux médias restants** pour demander une autorisation écrite, en décrivant l'usage : un résumé reformulé de quelques lignes, le nom du média, un lien vers l'article. Ou passer par leur service de licences, par exemple Vox Media ou Dow Jones Reprints.
2. **Garder ceux qui répondent** et retirer les autres de `sources.json`.
3. **Conserver** les réponses écrites.

Tant que l'app reste en test, sans publication ni revenu, le risque est faible. Il ne l'est plus une fois l'app publiée.

# Atlas — Agent de recherche web IA

**Atlas** est un agent IA qui cherche **sur tout le web** pour vous : produit,
loi, méthode, comparaison, actualité… Vous posez une question, il analyse le
sujet, interroge DuckDuckGo, lit les meilleures pages, puis vous rend une
**synthèse approfondie et sourcée** avec points clés et conclusion claire.

L'interface de communication est un simple chat dans le navigateur —
aucune installation lourde, aucune clé API obligatoire.

## ✨ Ce qu'il fait

- **Il vous comprend même mal écrit** — fautes, abréviations, langage SMS :
  « salu c quoi un bitcoin stp c fiable ou pas » → il affiche
  `💡 compris : Qu'est-ce que le Bitcoin, est-ce un investissement fiable…`
  et cherche sur la version corrigée. Même langue que vous, toujours.
- **Recherche web illimitée** — DuckDuckGo, sans clé API, requêtes adaptées au
  sujet (produit → avis/prix, loi → texte officiel, tutoriel → étapes),
  ~18 résultats par question, pubs filtrées, et **un tour de recherche
  complémentaire automatique** si les premières sources sont faibles.
- **Lecture réelle des pages** — il ne se contente pas des extraits de
  résultats : il ouvre les meilleures pages et en lit le contenu.
- **Réponse structurée** — `Réponse directe` → `Analyse détaillée` →
  `Points clés` → `Conclusion`, avec citations `[1]`, `[2]` cliquables
  vers les sources.
- **Suivi en direct** — chaque étape défile dans le chat : analyse,
  recherche, lecture, rédaction ; la réponse arrive mot à mot.
- **Réponses qui tranchent** — confrontation des sources, alerte sur les
  chiffres contradictoires, conclusion nette et actionnable (jamais
  « cela dépend »).
- **Conversation** — les questions suivantes gardent le contexte.
- **Rapide** — 9 à 20 secondes par recherche (mesuré, voir plus bas).

## 🚀 Lancement

```bash
pip install -r requirements.txt
python run.py            # ouvre http://127.0.0.1:8787
```

Options : `python run.py --port 9000 --no-browser`.

Fonctionne sans aucune configuration si **Ollama** tourne en local
(`ollama serve`, modèle `qwen3:0.6b` par défaut).

### 🖥️ Mode fenêtre native (raccourci Windows)

Comme KIRA, Atlas peut tourner dans une **fenêtre d'application** (pywebview),
sans navigateur — c'est le mode du raccourci `E:\Raccourci-agent\Atlas.lnk` :

```bash
python -m venv .venv                          # déjà fait
.venv\Scripts\pip install pywebview -r requirements.txt
.venv\Scripts\pythonw launch_desktop.py       # fenêtre native Atlas
```

- fermer la fenêtre arrête le serveur avec (journal : `atlas_launch.log`) ;
- si un serveur tourne déjà sur le port, la fenêtre le réutilise ;
- `python run.py` reste disponible en mode navigateur.

## 🧠 Choix du cerveau (qualité / vitesse)

| Cerveau | Clé | Qualité | Vitesse observée |
|---|---|---|---|
| Gemini (réutilise `kira/.env` si `KIRA_CLOUD_AI=1`) | aucune si déjà là | très bonne | 9–20 s par recherche |
| Groq / OpenRouter / OpenAI (`.env` du projet) | gratuite (Groq) | très bonne | ~10 s |
| Ollama local `qwen3:0.6b` | aucune | correcte | 40–90 s (CPU) |

Résolution : `ATLAS_LLM_PROVIDER=auto` (défaut) prend la première clé
disponible, sinon Ollama. Forcer le local : `ATLAS_LLM_PROVIDER=ollama`.

Robustesse intégrée :

- **Rotation de modèles** — le modèle principal part du plus fiable ; s'il
  répond `503` (saturation), Atlas essaie immédiatement la chaîne de secours
  (`3.5-flash-lite`, `3.8-flash`, `3.1-flash-lite`).
- **Reprise automatique** — si le flux est coupé en plein milieu, la réponse
  partielle est effacée (`restart`) et régénérée avec le modèle suivant ;
  si le cloud entièrement indisponible, Ollama prend le relais (prompt
  reconstruit au contexte local) et l'interface l'indique.
- **Recherche résiliente** — plusieurs backends DuckDuckGo
  (défaut → `lite` → `html`) avec préférence mémorisée : les rate-limits
  d'usage intensif ne bloquent plus l'agent.

## ⚡ Mesures (cet ordinateur, sans GPU)

| Question | Temps total | 1er mot | Sources |
|---|---|---|---|
| « Quelles sont les obligations de la loi RGPD pour un site web ? » | **12,0 s** | 9,0 s | 18 |
| « loi sur les donnne personel en franc est obligatoi ou pas » (mal écrit) | **15,9 s** | 11,4 s | 18 |
| « Comparer iPhone 17 et Samsung Galaxy S26 » | **17,8 s** | 14,5 s | 16 |
| « Quels sont les meilleurs vélos électriques pour la ville ? » | **17,4 s** | 13,5 s | 18 |
| « Et quel est le prix moyen de ces vélos ? » (suivi) | **9,0 s** | — | 18 |

Fourchette observée : **12 à 38 s** selon la saturation du fournisseur cloud
(les rotations de modèles en cas de `503` ajoutent quelques secondes) ;
la compréhension du texte et la planification tournent **en parallèle** de la
première recherche, elles n'ajoutent aucun temps d'attente.

Le parallélisme explique le gain : la question brute part en recherche
**pendant** que le modèle planifie les requêtes, et les pages se lisent
**pendant** les recherches complémentaires.

## 🏗️ Architecture

```
research-agent/
├── run.py               # point d'entrée : serveur + navigateur
├── atlas/
│   ├── config.py        # .env, détection du cerveau, budgets de contexte
│   ├── search.py        # DuckDuckGo multi-backends, filtres, dédoublonnage
│   ├── fetch.py         # lecture parallèle des pages + extraction lxml
│   ├── llm.py           # streaming Ollama / OpenAI-compatible, rotation, replis
│   ├── agent.py         # orchestration : planifier → chercher → lire → synthétiser
│   └── server.py        # HTTP local : statique + API en flux NDJSON
├── web/                 # interface (HTML/CSS/JS, sans dépendance)
├── .env.example
└── requirements.txt     # ddgs, httpx, lxml
```

### API

- `GET /api/status` — cerveau et moteur actuels
- `POST /api/research` — corps `{message, history}` → flux **NDJSON** :
  `step` (étapes), `sources`, `token` (synthèse en direct), `done`, `error`

L'interface est mono-page : elle affiche les étapes, les pastilles de
sources numérotées, le markdown (titres, listes, gras) et transforme les
citations `[2]` / `[2, 5]` en liens vers les pages citées. Le bouton
**Arrêter** interrompt nettement une recherche en cours.

## 🐛 Dépannage

- **« Aucun résultat de recherche »** — vérifiez la connexion ; réessayez
  dans quelques secondes (rate-limit DuckDuckGo transitoire).
- **Réponse lente ou « 503 »** — le cloud sature : la rotation de modèles
  et le repli local s'en chargent ; relancer relance l'essai.
- **Ollama indisponible** — `ollama serve`, puis `ollama list`.
- **Port occupé** — `python run.py --port 9000`.
- **Tout en local (privacy)** — `ATLAS_LLM_PROVIDER=ollama` dans `.env`.

## 🔒 Confidentialité

- La question posée part vers : DuckDuckGo (recherche) et le cerveau choisi
  (synthèse). Aucune autre donnée ne quitte la machine.
- Les clés restent dans les fichiers `.env` (jamais commités).
- L'historique de conversation vit dans l'onglet du navigateur : il n'est
  pas enregistré sur le disque.

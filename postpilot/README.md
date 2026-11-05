# PostPilot

**Agent autonome de gestion et d'automatisation des réseaux sociaux.**

Projet **totalement indépendant de KIRA** : tout vit dans `E:\postpilot`
(code, données, sessions, journaux). Aucun fichier partagé avec les autres agents.

---

## Démarrage

| Fichier | Rôle |
|---|---|
| `lancer_postpilot.bat` | **Mode fenêtre** (recommandé) — ouvre PostPilot dans une fenêtre native |
| `lancer_postpilot_navigateur.bat` | Mode navigateur — ouvre l'interface dans Chrome |
| `run.py` | Point d'entrée Python (`python run.py`) |
| `launch_desktop.py` | Fenêtre native (pywebview), journal dans `socia_launch.log` |

Interface : **http://127.0.0.1:8790**

---

## Utilisation

### 1. Brancher vos comptes

Dans « Mes comptes connectés », donnez l'adresse de votre profil Facebook,
Instagram ou TikTok puis cliquez sur **Ouvrir la fenêtre**.

La fenêtre réelle du réseau s'affiche à l'écran : **c'est vous qui vous
connectez**, PostPilot ne touche jamais à vos identifiants. La session est
mémorisée dans `data/sessions/<plateforme>` — vous restez connecté entre deux
lancements.

### 2. Programmer une publication

Écrivez une phrase en français :

> `Publie ce post toutes les 1 heure sur mon compte Facebook`

ou, pour les groupes :

> `Partage dans mes groupes facebook toutes les 4 heures`

L'agent comprend : plateforme, fréquence, type (post / vidéo / story),
destination (profil ou groupes), contenu entre guillemets.

Champs complémentaires dans « Options » : contenu, fichier média
(**requis pour Instagram et TikTok**), URL du groupe, fréquence en secondes.

### 3. Suivre le travail

- **Tâches programmées** : prochaine exécution, nombre de passages, dernier
  résultat, boutons *Lancer maintenant / Pause / Supprimer*.
- **Fenêtres des réseaux** : les fenêtres Chrome sont visibles en temps réel.
- **Journal de bord** : chaque étape est tracée.

---

## Architecture

```
E:\postpilot\
├── run.py                  # serveur + interface
├── launch_desktop.py        # fenêtre native (pywebview)
├── lancer_socia.bat         # raccourci bureau
├── requirements.txt
├── socia\
│   ├── config.py            # chemins locaux
│   ├── store.py             # comptes / tâches / journal (JSON)
│   ├── commands.py          # parseur de commandes françaises
│   ├── scheduler.py         # planificateur (thread, exécution auto)
│   ├── browser.py           # Playwright VISIBLE, 1 thread dédié
│   ├── agent.py             # orchestrateur
│   ├── server.py            # API HTTP locale
│   └── platforms\           # facebook / instagram / tiktok
├── web\                     # interface (HTML/CSS/JS + logo)
├── tests\                   # 15 tests (pytest)
└── data\                    # comptes, tâches, journaux, sessions, médias
```

### Points techniques

- **Fenêtres toujours visibles** : `headless=False` — vous voyez chaque
  publication se faire.
- **Sessions persistantes** : profils Chrome par plateforme, les cookies
  survivent aux redémarrages.
- **Un seul thread navigateur** : l'API sync de Playwright est liée au thread
  qui l'a lancée ; un `ThreadPoolExecutor(max_workers=1)` évite les conflits
  avec le serveur HTTP multi-threads.
- **Nettoyage des profils verrouillés** : si un Chrome orphelin garde le
  profil, il est fermé automatiquement au lancement.
- **API non bloquante** : `/api/state` répond en quelques millisecondes même
  pendant une publication.

---

## Tests

```bash
.venv\Scripts\python.exe -m pytest tests -q
```

15 tests : parseur français, stockage, planificateur, création de tâches.

---

## Prérequis

- Python 3.11+
- Google Chrome ou Microsoft Edge installé
- `pip install -r requirements.txt` (Playwright, pywebview)

---

## À savoir

- Instagram et TikTok **exigent un fichier** (photo/vidéo) : un post texte
  seul n'existe pas sur ces plateformes.
- Publier trop souvent peut déclencher des limites anti-spam des réseaux :
  restez raisonnable (≥ 1 publication/heure par compte est un ordre de
  grandeur sûr).
- PostPilot ne stocke **aucun mot de passe** — seulement vos URL de profil et
  la session navigateur locale sur `E:`.

# Lecteur NeurIPS 2026

Une page web locale pour explorer les papers NeurIPS 2026 par « fils de réflexion », avec des résumés générés à la demande par DeepSeek et adaptés à ton profil de lecteur (domaine, niveau, points à mettre en avant).

## Ce qu'il te faut

- **Python 3** (aucune bibliothèque à installer).
- **Une clé API DeepSeek** : crée un compte sur <https://platform.deepseek.com>, ajoute un peu de crédit, puis crée une clé (rubrique « API keys »). Les résumés sont facturés sur ton compte, mais chacun n'est généré qu'une fois (mis en cache ensuite).
- **Une connexion Internet** : la vue 3D charge three.js depuis un CDN, et les résumés appellent l'API DeepSeek.

## Installation

**Linux / macOS**

```bash
git clone URL_DU_REPO
cd NOM_DU_REPO
cp .env.example .env
nano .env        # remplace sk-xxxx... par ta clé, puis Ctrl+O, Entrée, Ctrl+X
```

**Windows (PowerShell)**

```powershell
git clone URL_DU_REPO
cd NOM_DU_REPO
copy .env.example .env
notepad .env     # remplace sk-xxxx... par ta clé, puis enregistre
```

Remplace `URL_DU_REPO` et `NOM_DU_REPO` par ceux de ce dépôt. Le fichier `.env` reste sur ta machine : il n'est jamais envoyé sur GitHub.

## Lancement

Depuis le dossier `lecteur/` :

```bash
cd lecteur
python ../serveur.py
```

Selon ton système, la commande peut être `python3 ../serveur.py`.

Ouvre ensuite <http://localhost:8000> dans ton navigateur. Garde le terminal ouvert tant que tu utilises la page, et arrête avec `Ctrl+C`.

## Premier lancement : ton profil

À la première ouverture, la page te demande ton profil. Un profil de départ est déjà rempli : modifie-le pour qu'il te corresponde, puis clique sur « Enregistrer et ouvrir le lecteur ».

- **Qui es-tu ?** : ton domaine, ce que tu maîtrises, ce qu'il faut t'expliquer. Exemple : « Le lecteur est ingénieur en neurosciences cognitives. Il connaît bien les statistiques et le signal EEG, mais pas le jargon des LLM. Explique brièvement tout terme de deep learning. »
- **Priorité (facultatif)** : ce que les résumés doivent mettre en avant. Exemple : « Dans idée, commence par les hypothèses de départ du paper. »

Pour changer de profil plus tard, ouvre <http://localhost:8000/profil.html>. Les résumés déjà générés avec un autre profil ne sont pas réutilisés : ils sont régénérés avec le nouveau (le premier clic est donc un peu plus long).

## Utilisation

- Clique sur un fil ou un paper pour afficher son résumé, rédigé pour ton profil.
- Chaque point est accompagné d'une explication en mots simples.
- La « version plus simple » reste disponible en un clic.
- Les résumés sont mis en cache dans `lecteur/data/cache_resumes.json` : un second clic sur le même élément est instantané et gratuit.

## Dépannage

- **« Clé DeepSeek introuvable »** : le fichier `.env` n'existe pas (ou pas à la racine du repo), ou la clé est encore `sk-xxxx...`. Le nom de la variable doit contenir `DEEPSEEK`.
- **Erreur de port occupé** : un autre serveur utilise déjà le port 8000. Ferme-le, ou arrête l'ancien terminal avec `Ctrl+C`.
- **Rien ne s'affiche au clic** : ouvre bien <http://localhost:8000> (et non le fichier `fils.html` directement), puis recharge avec `Ctrl+Maj+R`.
- **Page sans 3D** : vérifie ta connexion Internet.

## Structure

```
serveur.py            serveur local + appels DeepSeek + cache
.env.example          modèle pour ta clé API
lecteur/
  fils.html           la page principale
  profil.html         la page de configuration du profil
  data/               données des papers et des fils
```

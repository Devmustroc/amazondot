# Démarrage Rapide (60 secondes)

SovereignDot est conçu pour être testé immédiatement, même si vous ne possédez pas encore d'Amazon Echo Dot jailbreaké. Grâce au **Mode Émulateur PC**, vous pouvez interagir avec l'assistant directement via le micro et les haut-parleurs de votre ordinateur !

---

## 💻 Option A : Mode Émulateur PC (Sans Matériel)

Le mode émulateur remplace la connexion TCP de l'Echo Dot par une passerelle audio locale utilisant votre carte son (compatible Linux, macOS et Windows).

### 1. Cloner le Dépôt

```bash
git clone https://github.com/Devmustroc/amazondot.git
cd amazondot
```

### 2. Créer l'Environnement Virtuel

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configurer l'Environnement

Copiez le template de configuration :

```bash
cp .env.example .env
```

Éditez le fichier `.env` pour définir le mode émulateur :

```ini
AUDIO_INPUT_MODE=local
OPENROUTER_API_KEY=votre_cle_openrouter_optionnelle
```

*(Si vous n'avez pas de clé OpenRouter, SovereignDot utilise automatiquement votre instance locale Ollama ou les intentions hors-ligne).*

### 4. Lancer SovereignDot

```bash
python -m core_server.main
```

Au premier démarrage, SovereignDot télécharge automatiquement le modèle de synthèse vocale Piper (63 Mo) et initialise votre coffre Obsidian local dans `./vault/Memory/`. Vous pouvez **taper votre commande au clavier** ou **appuyer sur Entrée à vide pour enregistrer 4 secondes depuis votre microphone** :

> **« Régis, quelle heure est-il ? »**  
> **« Régis, qui es-tu ? »**  
> **« Régis, retiens que Ismail adore jouer aux échecs. »**

---

## 🐳 Option B : Déploiement Docker Homelab

Si vous souhaitez faire tourner le serveur sur votre machine Proxmox, un NAS ou un serveur domestique :

```bash
# Lancer le serveur avec Docker Compose
docker compose up -d --build

# Consulter les journaux en direct
docker compose logs -f sovereigndot
```

Le fichier `docker-compose.yml` est préconfiguré en `network_mode: host` pour permettre l'écoute instantanée sur le port `TCP:9001` de l'Echo Dot.

---

## 📡 Option C : Avec l'Amazon Echo Dot 2G Libéré

Une fois votre Echo Dot jailbreaké (voir le [Guide Hardware](../hardware/echo-dot-2g.md)) :

1. Démarrez l'Echo Dot sur votre réseau Wi-Fi local.
2. Vérifiez que le daemon `tad_dotd` tourne sur l'Echo Dot (ports 9000/9001).
3. Définissez l'IP de l'enceinte dans votre fichier `.env` :

```ini
AUDIO_INPUT_MODE=echo_dot
DOT_HOST=192.168.1.23
DOT_MIC_PORT=9000
DOT_PLAY_PORT=9001
```

4. Lancez le serveur : il se connecte immédiatement au transducteur audio de l'Echo Dot.

---

## 🧪 Vérifier le Fonctionnement (Tests Unitaires)

Vous pouvez exécuter l'ensemble de la suite de tests automatisés à tout moment :

```bash
python -m unittest discover tests
```

Tous les tests (STT, TTS, Circuit-Breaker, VoiceID, MCP, Intent Registry) doivent s'exécuter en moins de 6 secondes avec un statut vert `OK`.

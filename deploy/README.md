# 🚀 TAD Core — Guide de Déploiement Production (Proxmox CT 105)

Ce dossier contient l'infrastructure de conteneurisation et de supervision systemd pour faire tourner **TAD Core (Régis)** 24/7 sur le conteneur LXC Docker-host (CT 105) hébergé sur le serveur Proxmox VE (`192.168.1.200`).

---

## 🏛️ 1. Architecture de Déploiement

- **Hôte** : Proxmox VE (`192.168.1.200`)
- **Conteneur d'exécution** : LXC CT 105 (`docker-host`), Debian 12
- **Image Docker** : `tad-core:latest` basée sur `python:3.12-slim-bookworm` (Multi-stage build)
- **Réseau** : `network_mode: host` pour éliminer le surcoût de virtualisation réseau et permettre la communication native ultra-basse latence avec :
  - **Echo Dot 2G** : `192.168.1.23` (port 9000 audio PCM brut, port 9001 audio play tinyctlplay, port 9002 événements matériel)
  - **Ollama local** : `127.0.0.1:11434`
  - **Proxmox SRE API** : `192.168.1.200:8006`

---

## 📦 2. Fichiers Disponibles

| Fichier | Rôle |
|---|---|
| `Dockerfile` | Image multi-stage légère avec dépendances C/audio et modèle Piper ONNX pré-chargé |
| `docker-compose.yml` | Déclaration du service conteneurisé avec volumes persistants et limites de ressources |
| `tad-core.service` | Unité systemd de supervision automatique avec auto-restart |
| `deploy_ct105.sh` | Script d'automatisation de déploiement en production avec healthcheck direct |
| `../core_server/healthcheck.py` | Sonde de santé autonome vérifiant modèles, coffre chiffré et Echo Dot |

---

## ⚡ 3. Déploiement en 1 Ligne

Depuis la machine de développement, lancer :

```bash
./deploy/deploy_ct105.sh
```

Le script effectue automatiquement :
1. La validation de la connexion SSH sans mot de passe à Proxmox VE.
2. L'archivage propre du code source sans artefacts de test ni venv local.
3. Le transfert et l'extraction dans `/opt/tad` sur le CT 105.
4. La compilation de l'image Docker multi-stage.
5. Le démarrage du conteneur en arrière-plan.
6. L'activation du service systemd `tad-core.service`.
7. L'exécution de la sonde `healthcheck.py`.

---

## 🛠️ 4. Commandes d'Exploitation Usuelles

### Suivre les logs en direct
```bash
# Via Docker
ssh root@192.168.1.200 "pct exec 105 -- docker logs -f tad-core"

# Via Systemd Journald
ssh root@192.168.1.200 "pct exec 105 -- journalctl -u tad-core.service -f"
```

### Vérifier la santé du conteneur
```bash
ssh root@192.168.1.200 "pct exec 105 -- docker exec tad-core python -m core_server.healthcheck"
```

### Redémarrer le service
```bash
ssh root@192.168.1.200 "pct exec 105 -- systemctl restart tad-core.service"
```

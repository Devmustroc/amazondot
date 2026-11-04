#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Assurer que le conteneur tourne en tâche de fond
if [ -z "$(docker ps -q -f name=amazondot-claude-code)" ]; then
    echo "📦 Démarrage du conteneur Claude Code..."
    docker compose up -d --build
fi

# Exécuter Claude Code interactivement à l'intérieur
echo "🚀 Lancement de Claude Code..."
docker compose exec -it -w /workspaces/amazondot -u node claude-code claude "$@"

# Mémoire Long-Terme Obsidian (Markdown)

Contrairement aux assistants fermés qui stockent vos préférences dans des bases de données opaques sur des serveurs distants, SovereignDot utilise une approche **100% transparente, durable et interopérable** : vos souvenirs vocaux sont rédigés directement sous forme de notes **Markdown** lisibles dans votre coffre **Obsidian** ([`core_server/obsidian_memory.py`](file:///home/devmust/Work/amazondot/core_server/obsidian_memory.py)).

---

## 📂 Organisation Atomique du Coffre

Les informations apprises par SovereignDot sont catégorisées et écrites avec horodatage ISO dans le répertoire configuré (`OBSIDIAN_VAULT_PATH` ou `./vault/Memory/`) :

```text
vault/Memory/
├── Famille.md      # Préférences, anniversaires, activités des enfants
├── Homelab.md      # Configuration réseau, IP, ports, topologie serveurs
├── Santé.md        # Allergies, traitements, médecins traitants
└── Divers.md       # Notes générales et mémos éphémères
```

Chaque entrée est stockée sous forme de puce avec date et heure :

```markdown
# Mémoire Famille

- [2026-11-08 20:30] Ismail adore jouer aux échecs.
- [2026-11-08 21:15] Le mot de passe du wifi invité est bienvenue2026.
- [2026-11-08 22:00] Ismail a cours de natation tous les samedis matin à 10h.
```

---

## 🎙️ Commandes Vocales d'Apprentissage & Rappel

### 1. Apprentissage Instantané (0 ms de latence LLM)

Pour faire mémoriser une information à SovereignDot, utilisez l'une des formules de déclenchement :

> **« Régis, retiens que Ismail adore jouer aux échecs. »**  
> **« Régis, note que le code du portail est 4589. »**  
> **« Régis, enregistre que le serveur Proxmox sauvegarde à 3h du matin. »**

SovereignDot classe automatiquement l'information, l'écrit sur le disque et confirme immédiatement :
> *« C'est bien noté dans ma mémoire Famille, j'ai enregistré que Ismail adore jouer aux échecs. »*

### 2. Rappel Vocal Sémantique

Pour interroger la mémoire de l'assistant sans passer par Internet :

> **« Régis, que sais-tu sur les échecs ? »**  
> **« Régis, rappelle-moi ce que j'ai dit sur le wifi. »**  
> **« Régis, parle-moi de la natation. »**

L'assistant consulte directement le fichier Markdown correspondant et répond :
> *« D'après mes notes dans Famille : Ismail adore jouer aux échecs. »*

---

## 🧠 Injection Contextuelle dans le Prompt LLM

Lorsqu'une question complexe est adressée au modèle de langage (OpenRouter ou Ollama), SovereignDot recherche les lignes les plus pertinentes dans votre coffre Obsidian et les injecte automatiquement dans le prompt système :

```text
[SYSTEM PROMPT]
Date et heure courantes: Dimanche 08 Novembre 2026 à 22:30
Locuteur identifié: El Mustapha (Rôle: admin)

Contexte et mémoire connus:
- Ismail adore jouer aux échecs.
- Ismail a cours de natation tous les samedis matin à 10h.
```

Le LLM peut ainsi répondre avec une personnalisation chirurgicale, sans que vos données personnelles n'aient jamais été indexées par un moteur d'entraînement tiers.

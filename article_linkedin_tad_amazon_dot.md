# Comment j'ai transformé un vieil Echo Dot en assistant IA souverain (sans être ingénieur embarqué)

Comme beaucoup de développeurs, j'avais un vieil Amazon Echo Dot 2G qui prenait la poussière. Le matériel audio est excellent (7 micros en beamforming, bon DAC), mais l'appareil est bridé par un écosystème fermé.

J'ai voulu relever un défi : **enlever tous les services Amazon, récupérer le flux audio brut et brancher l'enceinte sur une stack IA moderne et locale**, connectée à mon Homelab et à mes notes Obsidian.

Je suis développeur logiciel avec des bases en C apprises durant mes études (pointeurs, mémoire, sockets), mais je n'avais jamais fait de reverse-engineering bas niveau ni touché aux pilotes audio Linux. 

Voici comment j'ai conçu ce projet en m'appuyant sur des outils de pair-programming IA (**Claude 3.7 Sonnet**, **Gemini 3.8 Flash**, le skill **REA** et les méthodes de **Matt Pocock**).

---

## 1. La prise de contrôle du matériel

L'Echo Dot 2G tourne sur un SoC Mediatek MT8163 sous une base Android modifiée. 

Pour récupérer la main sur l'appareil :
1. **Root & Bootloader** : Utilisation d'un exploit bootrom public (`amonet`) pour déverrouiller l'accès root avec Magisk.
2. **Nettoyage** : Neutralisation des services d'écoute et des applications Amazon en arrière-plan.
3. **Contrôle système** : Remplacement de l'animation de démarrage d'origine par un script personnalisé pour contrôler l'anneau de LEDs dès le boot.

---

## 2. Le défi audio : faire du C natif pour réduire la latence

Au début, faire transiter l'audio via des commandes shell ou des ponts ad-hoc ajoutait plus d'une seconde de latence. Pour un assistant vocal, c'est inutilisable.

J'ai donc écrit deux petits démons natifs en C :

### `tad_dotd` : streamer les micros en TCP
La matrice capture 9 canaux audio bruts en 24 bits (format `S24_3LE`). Le démon C lit directement ces trames matérielles ALSA et diffuse le canal du micro central en temps réel sur une socket TCP locale vers mon serveur.

### `tad_buttonsd` : acoustique et zéro souffle
Sur le plan audio, le haut-parleur de 35 mm et son ampli posaient deux soucis :
- Les basses fréquences faisaient saturer le petit boîtier plastique.
- L'amplificateur émettait un léger souffle audible en veille.

J'ai résolu ça avec deux ajustements :
- **Un filtre passe-haut à 220 Hz** et un limiteur dans le traitement audio pour éviter l'écrêtage.
- **Un mute matériel via GPIO** : dès que l'enceinte ne joue aucun son, le démon C coupe physiquement l'amplificateur. Résultat : zéro souffle en veille.

---

## 3. Le cerveau hybride : rapide en local, puissant dans le cloud

Pour les réponses, il fallait concilier deux besoins : la rapidité pour les commandes simples et la capacité de raisonnement pour les tâches complexes.

J'ai mis en place un **routeur intelligent (JEV)** :

```text
Microphone ➔ VAD (détection de voix) ➔ Whisper local ➔ Routeur JEV
                                                         ├── Simple   ➔ Hermes (Ollama local, < 700ms)
                                                         └── Complexe ➔ Gemini 3.8 Flash (via OpenRouter + MCP)
```

1. **La voie locale (< 700 ms)** : Les requêtes simples (l'heure, salutations, statut rapide) sont traitées en local par un modèle Hermes via Ollama.
2. **La voie cloud & outils** : Les questions techniques ou les commandes nécessitant d'interroger mon Homelab (surveillance réseau, monitoring Proxmox via MCP) basculent vers Gemini 3.8 Flash.

---

## 4. Une mémoire permanente dans Obsidian

Contrairement aux assistants classiques qui oublient tout à chaque phrase, j'ai relié le système à mon coffre **Obsidian**.

Quand je dis *"Régis, retiens que..."*, le système extrait l'information et l'écrit dans un fichier Markdown structuré. À chaque nouvelle requête, le contexte utile de mon coffre est réinjecté dans le prompt du modèle. L'assistant retient mes préférences et mes configurations techniques sans passer par une base de données opaque.

---

## Ce que j'en retiens

- **Le matériel existant a de la valeur** : recycler de vieux objets connectés permet d'avoir du matériel de qualité sans dépendre d'un cloud propriétaire.
- **L'IA comme accélérateur d'ingénierie** : avec de bonnes bases d'ingénierie logicielle et une méthodologie rigoureuse, les LLMs permettent d'aborder des domaines pointus (embarqué, ALSA, bas-niveau) sans bloquer sur des détails de syntaxe ou des registres matériels obscurs.

---

*Disclaimer : Ce projet a été réalisé à des fins d'apprentissage et d'interopérabilité sur un matériel personnel (Directive européenne 2009/24/CE), totalement déconnecté des serveurs Amazon.*

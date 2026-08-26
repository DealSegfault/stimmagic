# Guide de Setup Modal (Interactif & Automatisé)

Consultez le manuel complet et détaillé : **[MAN_MODAL.md](MAN_MODAL.md)**

Depuis la racine du dépôt, préparez d'abord le runtime local (Codex CLI doit
déjà être connecté à ChatGPT) :

```bash
infra/bin/bootstrap-local.sh
```

Aucun compte Stimma ni clé API LLM n'est requis.

## 1. Démarrage Interactif (CLI / Codex / Terminal)

```bash
# Assistant interactif étape par étape
python3 infra/bin/setup-interactive.py
# ou
./infra/bin/setup-modal.sh -i
```

## 2. Démarrage Rapide 1-Ligne (Variables d'environnement)

```bash
export MODAL_TOKEN_ID="ak-..."
export MODAL_TOKEN_SECRET="as-..."

# Installation H3 complète, raccourci Bureau et lancement vérifié
./infra/bin/setup-modal.sh
```

`HF_TOKEN` est optionnel. S'il est absent, MiniMax H3 vidéo reste installé et
les extras sous licence Repaint/TRELLIS.2 sont ignorés.

## 3. Via Codex CLI / Agent Autonome

```bash
codex exec "Clone ce dépôt et termine l'installation avec \$stimma-local-setup. Les identifiants Modal sont déjà dans le contexte : ne les redemande pas et ne les écris dans aucun fichier."
```

À la fin d'une installation macOS validée, l'agent doit laisser
`Lancer Stimma.command` et `STIMMA - Installation terminée.txt` sur le Bureau.
Le mémo n'est créé qu'après le lancement de Stimma et la détection d'un outil
vidéo H3 disponible.

Consultez [MAN_MODAL.md](MAN_MODAL.md) pour les détails d'architecture, les options manuelles et le troubleshooting.

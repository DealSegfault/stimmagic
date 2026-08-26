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
export HF_TOKEN="hf_..."
export MODAL_TOKEN_ID="ak-..."
export MODAL_TOKEN_SECRET="as-..."

# Installation automatique de tous les conteneurs Modal
./infra/bin/setup-modal.sh
```

## 3. Via Codex CLI / Agent Autonome

```bash
codex exec "Configure ce dépôt avec le skill \$stimma-local-setup. Demande-moi les secrets au moment nécessaire et ne les écris jamais dans Git."
```

Consultez [MAN_MODAL.md](MAN_MODAL.md) pour les détails d'architecture, les options manuelles et le troubleshooting.

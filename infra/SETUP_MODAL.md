# Guide de Setup Modal (Interactif & Automatisé)

Consultez le manuel complet et détaillé : **[MAN_MODAL.md](file:///Users/mac/adp/comfy/MAN_MODAL.md)**

## 1. Démarrage Interactif (CLI / Codex / Terminal)

```bash
# Assistant interactif étape par étape
python3 bin/setup-interactive.py
# ou
./bin/setup-modal.sh -i
```

## 2. Démarrage Rapide 1-Ligne (Variables d'environnement)

```bash
export HF_TOKEN="hf_..."
export MODAL_TOKEN_ID="ak-..."
export MODAL_TOKEN_SECRET="as-..."

# Installation automatique de tous les conteneurs Modal
./bin/setup-modal.sh
```

## 3. Via Codex CLI / Agent Autonome

```bash
codex exec "python3 bin/setup-interactive.py --non-interactive --hf-token 'hf_...' --modal-token-id 'ak-...' --modal-token-secret 'as-...'"
```

Consultez [MAN_MODAL.md](file:///Users/mac/adp/comfy/MAN_MODAL.md) pour les détails d'architecture, les options manuelles et le troubleshooting.

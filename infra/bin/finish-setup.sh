#!/bin/sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Déploiement du service Modal..."
"$ROOT/bin/deploy.sh"

echo "Téléchargement des poids dans le Volume Modal (aucun poids local)..."
"$ROOT/bin/download-models.sh"

echo "Inventaire distant..."
cd "$ROOT"
modal run modal_h3.py::model_inventory

echo "Configuration terminée. Lancez bin/start-gateway.sh puis bin/start-stimma.sh."

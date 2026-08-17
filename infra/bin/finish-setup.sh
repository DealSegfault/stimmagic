#!/bin/sh
set -eu

ROOT=/Users/mac/adp/comfy

echo "Déploiement du service Modal..."
"$ROOT/bin/deploy.sh"

echo "Téléchargement des poids dans le Volume Modal (aucun poids local)..."
"$ROOT/bin/download-models.sh"

echo "Inventaire distant..."
cd "$ROOT"
modal run modal_h3.py::model_inventory

echo "Configuration terminée. Lancez bin/start-gateway.sh puis bin/start-stimma.sh."

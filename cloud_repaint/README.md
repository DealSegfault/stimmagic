# Stimma Repaint cloud

L'intégration suit l'architecture H3 : les poids sont préparés une fois dans
un volume Modal persistant, puis l'endpoint cloud ne monte que ce volume pour
l'inférence.

```sh
# Bootstrap unique (HF_TOKEN sert uniquement à ce téléchargement)
modal secret create huggingface HF_TOKEN=...
/Users/mac/adp/comfy/bin/download-repaint-models.sh

# Déploiement de l'endpoint (aucun secret HF au runtime)
/Users/mac/adp/comfy/bin/deploy-repaint.sh
```

Configure ensuite le bridge H3 avec `REPAINT_MODAL_URL`. Il réutilise
`MODAL_PROXY_TOKEN_ID` et `MODAL_PROXY_TOKEN_SECRET`; l'ASGI Modal applique la
même authentification proxy que H3. Le service d'inpainting utilise une NVIDIA
L40S 48 GB à la demande et se met à zéro après 180 secondes.

Le token Hugging Face peut être requis car FLUX.1 Fill est soumis à une
autorisation d'accès sur Hugging Face. Il n'est jamais lu par le worker
d'inférence : `local_files_only=True` rend les cold starts indépendants de HF
une fois le volume préparé.

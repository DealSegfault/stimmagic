#!/bin/sh
set -eu

cd /Users/mac/adp/comfy
modal deploy --strategy recreate modal_h3.py

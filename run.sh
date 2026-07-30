#!/bin/bash
# MinerU batch runner — processes a PDF to structured Markdown
# Usage: ./run.sh paper.pdf [output_dir]

PAPER="${1:?Usage: ./run.sh paper.pdf [output_dir]}"
OUT="${2:-output}"

PYTHONPATH= D:/mineru_py310/Scripts/mineru.exe -p "$PAPER" -o "$OUT" -b pipeline

echo ""
echo "Done: $OUT/$(basename "$PAPER" .pdf)/auto/$(basename "$PAPER" .pdf).md"

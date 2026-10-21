#!/bin/sh
# Executado só quando o Coolify (ou outro serviço) monta o projeto com o Nixpacks.
# O GMP Tradutor precisa do Build Pack "Dockerfile"; aqui só explicamos isso no log.
echo "=================================================================="
echo "ERRO: este container foi montado com o NIXPACKS."
echo "O GMP Tradutor precisa do Build Pack DOCKERFILE."
echo ""
echo "No Coolify: Configuration > General > Build Pack > Dockerfile,"
echo "clique em Save e depois em Redeploy."
echo "Ports Exposes: 8765"
echo "=================================================================="
exit 1

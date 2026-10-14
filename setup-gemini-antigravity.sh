#!/usr/bin/env bash
set -e

echo "=== Iniciando Provisionamento do Ecossistema Google Gemini & Antigravity (Zero-Config Model) ==="

# 1. Garantir estrutura de pastas e link simbolico do GEMINI.md
mkdir -p .agents/workflows .agents/rules .agents/lib
if [ -f ".agents/gemini-antigravity.md" ]; then
  ln -sf .agents/gemini-antigravity.md GEMINI.md
  echo "[OK] Link simbolico GEMINI.md -> .agents/gemini-antigravity.md configurado."
fi

# 2. Instalar CLIs Globais e Servidores MCP Base (Node.js)
if command -v npm >/dev/null 2>&1; then
  echo "=== Instalando CLIs Globais (Firebase Tools, Genkit CLI) ==="
  npm install -g firebase-tools@latest genkit-cli@latest

  if [ -f "package.json" ]; then
    echo "=== Instalando SDKs Web & Backend (@google/genai, firebase, genkit, zod) ==="
    npm install @google/genai firebase genkit @genkit-ai/google-genai @genkit-ai/firebase zod
  fi
else
  echo "[AVISO] npm nao encontrado. Instale o Node.js 20+ para suporte Web e MCP."
fi

# 3. Instalar SDKs Python (Antigravity SDK, Google GenAI, Google ADK)
if command -v python3 >/dev/null 2>&1; then
  echo "=== Configurando Ambiente Python para Agentes (GenAI, ADK, Antigravity) ==="
  if [ ! -d ".venv" ]; then
    python3 -m venv .venv
  fi
  source .venv/bin/activate
  pip install --upgrade pip
  pip install google-genai google-adk pydantic python-dotenv
  pip install google-antigravity || echo "[INFO] Pacote google-antigravity requer canal especifico do ambiente Antigravity."
else
  echo "[AVISO] python3 nao encontrado. Pule se o projeto for exclusivamente Web/JS."
fi

# 4. Configurar Flutter / Dart (Mobile Cross-Platform) se o projeto usar Flutter
if command -v flutter >/dev/null 2>&1 && [ -f "pubspec.yaml" ]; then
  echo "=== Instalando Pacotes Flutter para Gemini e Firebase ==="
  dart pub global activate flutterfire_cli
  flutter pub add firebase_core firebase_auth cloud_firestore firebase_ai flutter_riverpod
fi

echo "=== Provisionamento Concluido com Sucesso! ==="

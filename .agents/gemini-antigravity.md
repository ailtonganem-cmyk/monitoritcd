# Diretrizes de Engenharia: Ecossistema Google Gemini & Antigravity

## 1. Regras de Ouro de Fluxo de Trabalho e Entrega de Código
1. **Código Completo e Sem Omissões:** Ao realizar qualquer alteração em qualquer arquivo do projeto, apresente SEMPRE o código completo e atualizado do arquivo alterado. É estritamente proibido omitir partes do código por brevidade ou usar comentários como `// ... resto do código permanece igual`.
2. **Execução Sequencial (Um Arquivo por Vez):** Trabalhe em apenas UM arquivo por vez. Apresente o código completo do arquivo modificado e aguarde a aprovação explícita ("ok") do gerente do projeto antes de avançar para o próximo arquivo. **Escopo (ajuste aprovado pelo Ailton):** esta regra vale somente quando o Ailton estiver acompanhando a sessão; NÃO se aplica nos modos `/autonomo`, `/loopcontinuo` e `/producao`, em que o agente segue sem aguardar "ok" a cada arquivo.
3. **Verificação via MCP antes da Conclusão:** Utilize os servidores MCP configurados (Chrome DevTools, Firebase, GitHub, Figma e Filesystem) para validar schemas, regras de autenticação e erros de console antes de apresentar a entrega.

## 2. Resolução Automática de Modelos (Zero-Config Auto-Discovery)
- **Proibição de Indicação Manual de Modelos:** O desenvolvedor NUNCA deve precisar informar, configurar ou alterar nomes de modelos (nem no código-fonte, nem em arquivos `.env`).
- **Auto-Descoberta no Código:** Toda integração com a IA do Google deve utilizar os módulos de resolução automática (`.agents/lib/gemini-auto-client.ts` para TypeScript/JavaScript/Web ou `.agents/lib/gemini_auto_client.py` para Python).
- **Funcionamento do Método Automático:**
  1. O próprio método consulta dinamicamente os modelos disponíveis na conta/API do Google (`models.list`) ou percorre a cadeia de aliases dinâmicos oficiais (somente aliases `-latest`, do mais forte para o mais leve: `gemini-pro-latest`, `gemini-flash-latest`; nunca nomes de versão fixos).
  2. Filtra apenas modelos ativos compatíveis com `generateContent`, ordenando automaticamente pela versão estável mais recente disponível.
  3. Armazena o modelo resolvido em cache de memória durante a sessão.
  4. Possui fallback automático (Self-Healing): caso o modelo selecionado retorne erro de indisponibilidade, descontinuação (`404`) ou limite (`429`), o método alterna automaticamente para o próximo modelo disponível do Google e reexecuta a chamada de forma transparente.
- **Execução no Antigravity CLI / IDE:** Os agentes devem utilizar sempre o modelo nativo da sessão ativa do Antigravity sem exigir flags manuais de modelo.

## 3. Padrões de Arquitetura Web (TypeScript / Angular / JS / Firebase)
- **Projetos Frontend / Hospedagem Estática (GitHub Pages / Firebase Hosting):**
  - Nunca exponha chaves da Gemini Developer API diretamente no código frontend público.
  - Utilize o SDK **Firebase AI Logic** (`firebase/ai`) autenticado via **Firebase Authentication** e protegido pelo **Firebase App Check**, encapsulado pelo resolvedor automático com fallback transparente.
  - Mantenha a integração limpa e modular com os serviços existentes do Firebase (Auth, Firestore, Realtime Database, Storage).
- **Projetos Fullstack / Node.js / TypeScript:**
  - Utilize exclusivamente o SDK unificado `@google/genai` através do cliente de auto-descoberta.
  - Para fluxos de backend e RAG, utilize **Firebase Genkit** com validação de schema via **Zod**.

## 4. Padrões de Arquitetura Mobile
- **Flutter (Android / iOS / Web):**
  - Utilize o pacote oficial `firebase_ai` integrado ao `firebase_core` e `firebase_auth`, encapsulando a inicialização do modelo em um método com fallback automático entre os aliases vigentes da API.
- **Android Nativo (Kotlin / Jetpack Compose):**
  - Priorize inferência híbrida combinando **Google AICore** (on-device) com fallback automático para nuvem via Firebase AI Logic.

## 5. Padrões de Sistemas Multiagentes (Python / TypeScript)
- Utilize o **Google ADK** (`google-adk` / `@google/adk`) e o **Google Antigravity SDK** (`google-antigravity`) consumindo o método `get_available_gemini_model()` do módulo `.agents/lib/gemini_auto_client.py`.
- Todas as respostas da IA consumidas por código devem utilizar **Structured Outputs** (`response_mime_type: "application/json"` + `response_schema`).

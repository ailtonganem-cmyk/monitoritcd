import { GoogleGenAI, GenerateContentConfig, GenerateContentResponse } from '@google/genai';
import { FirebaseApp } from 'firebase/app';
import { getAI, getGenerativeModel, GenerativeModel, GoogleAIBackend } from 'firebase/ai';

/**
 * Cadeia de prioridade automatica para resolucao dinamica e fallback
 * caso a listagem de modelos nao esteja acessivel no contexto cliente (browser).
 */
const DYNAMIC_FALLBACK_CHAIN: readonly string[] = [
  'gemini-pro-latest',
  'gemini-flash-latest'
];

export class GeminiAutoClient {
  private ai: GoogleGenAI;
  private cachedModels: string[] = [];
  private lastFetchTime = 0;
  private readonly cacheTtlMs = 1000 * 60 * 60; // 1 hora de cache em memoria

  constructor(apiKey?: string) {
    this.ai = new GoogleGenAI(apiKey ? { apiKey } : {});
  }

  /**
   * Consulta dinamicamente a API do Google, filtra modelos Gemini ativos
   * e ordena do mais recente/capaz para o mais leve.
   */
  public async discoverAvailableModels(forceRefresh = false): Promise<string[]> {
    const now = Date.now();
    if (!forceRefresh && this.cachedModels.length > 0 && now - this.lastFetchTime < this.cacheTtlMs) {
      return this.cachedModels;
    }

    try {
      const pager = await this.ai.models.list();
      const discovered: string[] = [];

      for await (const model of pager) {
        const name = (model.name || '').replace(/^models\//, '');
        const actions = model.supportedActions || [];
        const isGemini = name.startsWith('gemini-');
        const ExcludeSpecialized =
          !name.includes('embedding') &&
          !name.includes('imagen') &&
          !name.includes('veo') &&
          !name.includes('aqa') &&
          !name.includes('tts') &&
          !name.includes('audio');

        const supportsGenerate =
          actions.length === 0 || actions.includes('generateContent');

        if (isGemini && ExcludeSpecialized && supportsGenerate) {
          discovered.push(name);
        }
      }

      if (discovered.length > 0) {
        // Ordena priorizando versoes mais novas e estaveis
        discovered.sort((a, b) => b.localeCompare(a, undefined, { numeric: true }));
        this.cachedModels = Array.from(new Set([...discovered, ...DYNAMIC_FALLBACK_CHAIN]));
        this.lastFetchTime = now;
        return this.cachedModels;
      }
    } catch {
      // Se a chave ou ambiente restringir models.list(), utiliza a cadeia dinamica oficial
    }

    this.cachedModels = [...DYNAMIC_FALLBACK_CHAIN];
    this.lastFetchTime = now;
    return this.cachedModels;
  }

  /**
   * Executa a geracao de conteudo escolhendo o modelo disponivel automaticamente.
   * Se o modelo falhar por indisponibilidade/depreciacao/cota, tenta o proximo automaticamente.
   */
  public async generateContent(
    contents: string | Record<string, unknown> | Array<unknown>,
    config?: GenerateContentConfig
  ): Promise<GenerateContentResponse> {
    const models = await this.discoverAvailableModels();
    let lastError: unknown = null;

    for (const modelName of models) {
      try {
        return await this.ai.models.generateContent({
          model: modelName,
          contents: contents as string,
          config
        });
      } catch (error: unknown) {
        lastError = error;
        const errMessage = error instanceof Error ? error.message.toLowerCase() : String(error).toLowerCase();
        const isRecoverableModelError =
          errMessage.includes('404') ||
          errMessage.includes('not found') ||
          errMessage.includes('deprecated') ||
          errMessage.includes('429') ||
          errMessage.includes('quota') ||
          errMessage.includes('503') ||
          errMessage.includes('unavailable') ||
          errMessage.includes('not supported');

        if (!isRecoverableModelError) {
          throw error;
        }
      }
    }

    throw lastError || new Error('Nenhum modelo Google Gemini disponivel respondeu com sucesso.');
  }
}

/**
 * Wrapper Zero-Config para Frontend Web (GitHub Pages / Angular / JS com Firebase AI Logic).
 * Seleciona e alterna automaticamente o modelo disponivel sem precisar configurar nomes manualmente.
 */
export class FirebaseGeminiAutoClient {
  private firebaseApp: FirebaseApp;
  private activeModelIndex = 0;

  constructor(firebaseApp: FirebaseApp) {
    this.firebaseApp = firebaseApp;
  }

  private getModelInstance(modelName: string): GenerativeModel {
    const ai = getAI(this.firebaseApp, { backend: new GoogleAIBackend() });
    return getGenerativeModel(ai, { model: modelName });
  }

  public async generateContent(prompt: string): Promise<string> {
    let lastError: unknown = null;

    for (let i = 0; i < DYNAMIC_FALLBACK_CHAIN.length; i++) {
      const candidateIndex = (this.activeModelIndex + i) % DYNAMIC_FALLBACK_CHAIN.length;
      const modelName = DYNAMIC_FALLBACK_CHAIN[candidateIndex];

      try {
        const model = this.getModelInstance(modelName);
        const result = await model.generateContent(prompt);
        this.activeModelIndex = candidateIndex; // Mantem o modelo que funcionou em cache
        return result.response.text();
      } catch (error: unknown) {
        lastError = error;
      }
    }

    throw lastError || new Error('Nao foi possivel gerar resposta com nenhum modelo disponivel no Firebase AI.');
  }
}

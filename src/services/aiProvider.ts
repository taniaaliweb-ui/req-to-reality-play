// Provider-agnostic AI abstraction. No provider is configured in Phase 1.
// Future: OpenAI, Anthropic, local models, Hermes agent runtime — all behind this interface.
export interface AiRequest {
  role: "supervisor" | "research" | "story" | "audit";
  prompt: string;
  context?: Record<string, unknown>;
}
export interface AiResponse {
  text: string;
  provider: string;
  model: string;
}
export interface AiProvider {
  readonly id: string;
  readonly configured: boolean;
  complete(req: AiRequest): Promise<AiResponse>;
}

export class NotConfiguredProvider implements AiProvider {
  readonly id = "none";
  readonly configured = false;
  async complete(): Promise<AiResponse> {
    throw new Error("No AI provider configured. LifeSpan never fabricates AI output.");
  }
}

export const aiProvider: AiProvider = new NotConfiguredProvider();

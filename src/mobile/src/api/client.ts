/**
 * PosiPulse Mobile API Client
 * Interfaces directly with the FastAPI Gateway (OpenAPI 3.1).
 * Supports cursor pagination, offline fallbacks, and DPDP privacy requests.
 */

import { Article, FeedResponse, FeedbackPayload, DelistPayload, LanguageInfo, LanguagesResponse } from '../types';

export class PosiPulseApiClient {
  private baseUrl: string;

  constructor(baseUrl?: string) {
    // Default to localhost/loopback or environment configuration
    this.baseUrl = baseUrl || 'http://127.0.0.1:8000';
  }

  public setBaseUrl(url: string) {
    this.baseUrl = url;
  }

  /**
   * Fetch list of supported languages with metadata and directionality flags.
   */
  async getLanguages(): Promise<LanguageInfo[]> {
    const res = await fetch(`${this.baseUrl}/v1/languages`, {
      headers: { 'Accept': 'application/json' },
    });
    if (!res.ok) {
      throw new Error(`Failed to load languages: HTTP ${res.status}`);
    }
    const data: LanguagesResponse = await res.json();
    return data.languages;
  }

  /**
   * Fetch constructive article feed for a selected language and optional category.
   */
  async getFeed(
    language: string,
    options?: {
      category?: string;
      cursor?: string;
      limit?: number;
    }
  ): Promise<FeedResponse> {
    const params = new URLSearchParams();
    params.set('language', language);
    if (options?.category) params.set('category', options.category);
    if (options?.cursor) params.set('cursor', options.cursor);
    if (options?.limit) params.set('limit', String(options.limit));

    const res = await fetch(`${this.baseUrl}/v1/feed?${params.toString()}`, {
      headers: { 'Accept': 'application/json' },
    });
    if (!res.ok) {
      throw new Error(`Failed to load feed for ${language}: HTTP ${res.status}`);
    }
    return (await res.json()) as FeedResponse;
  }

  /**
   * Asynchronously record anonymous outbound referral click (DPDP Act 2023 compliant).
   */
  async recordClick(payload: {
    article_id: string;
    source_id: string;
    language: string;
    category_id?: number | null;
  }): Promise<void> {
    try {
      await fetch(`${this.baseUrl}/v1/analytics/click`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    } catch {
      // Fire-and-forget; never block the reader link-out
    }
  }

  /**
   * Submit constructive accuracy feedback or toxic positivity report.
   */
  async submitFeedback(payload: FeedbackPayload): Promise<{ success: boolean; feedback_id: string }> {
    const res = await fetch(`${this.baseUrl}/v1/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(`Failed to submit feedback: HTTP ${res.status}`);
    }
    return await res.json();
  }

  /**
   * Submit DPDP Act right to be forgotten / delisting request.
   */
  async submitDelist(payload: DelistPayload): Promise<{ success: boolean; message: string }> {
    const res = await fetch(`${this.baseUrl}/v1/privacy/delist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(`Failed to submit delist request: HTTP ${res.status}`);
    }
    return await res.json();
  }

  /**
   * Seed demo articles for automated test runs or offline previews.
   */
  async seedDemo(language: string): Promise<{ success: boolean; published_count: number }> {
    const res = await fetch(`${this.baseUrl}/v1/demo/seed?language=${encodeURIComponent(language)}`, {
      method: 'POST',
    });
    if (!res.ok) {
      throw new Error(`Failed to seed demo articles: HTTP ${res.status}`);
    }
    return await res.json();
  }

  /**
   * Dynamically fetch live news from publisher RSS feeds for the active language.
   */
  async fetchLive(language: string, force: boolean = false): Promise<{ success: boolean; result: any }> {
    const res = await fetch(
      `${this.baseUrl}/v1/ingest/live?language=${encodeURIComponent(language)}&force=${force}`,
      { method: 'POST' }
    );
    if (!res.ok) {
      throw new Error(`Failed to fetch live news: HTTP ${res.status}`);
    }
    return await res.json();
  }
}

export const apiClient = new PosiPulseApiClient();

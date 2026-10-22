/**
 * PosiPulse Mobile Client Types
 * Mirrors OpenAPI 3.1 specification and Pydantic Article schemas.
 * Guarantees zero raw publisher body text in client state.
 */

export type PositivityLabel = 'positive' | 'negative' | 'neutral' | 'toxic_positivity';

export type ReadingLevel = 'compact' | 'balanced' | 'deep_dive';

export interface PositivityMetadata {
  label: PositivityLabel;
  score: number;
  reason: string;
  rubric_version: string;
  category?: 'Science/Tech' | 'Ecology' | 'Empowerment' | 'Resilience' | 'Civic' | 'Sports' | 'Entertainment' | string;
}

export interface SummaryMetadata {
  text: string;
  model: string;
  prompt_version: string;
  verified: boolean;
  verifier_model?: string;
  verifier_score?: number;
  word_count: number;
}

export interface CategoryAssignment {
  primary_id?: number | null;
  secondary_ids: number[];
  subcategory_id?: string | null;
  confidence: number;
  taxonomy_version: string;
}

export interface Article {
  id: string;
  source_id: string;
  source_name: string;
  url: string;
  canonical_url: string;
  headline: string;
  published_at: string;
  fetched_at: string;
  language: string;
  cluster_id?: string;
  category?: CategoryAssignment | null;
  positivity: PositivityMetadata;
  summary: SummaryMetadata;
  status: 'published' | 'delisted' | 'held_hidden_category';
  publish_hold_reason?: string | null;
  is_rtl?: boolean;
}

export interface FeedResponse {
  articles: Article[];
  next_cursor?: string | null;
  total_returned: number;
}

export interface LanguageInfo {
  code: string;
  english_name: string;
  native_name: string;
  script: string;
  is_rtl: boolean;
  tier: 'tier_1' | 'tier_2' | 'tier_3';
  status: 'active' | 'evaluating';
  healthy_sources_count: number;
}

export interface LanguagesResponse {
  languages: LanguageInfo[];
}

export interface FeedbackPayload {
  article_id: string;
  feedback_type: 'not_positive' | 'toxic_positivity' | 'inaccurate_summary' | 'broken_link' | 'other';
  comments: string;
}

export interface DelistPayload {
  article_id: string;
  requester_name: string;
  requester_email: string;
  reason: string;
}

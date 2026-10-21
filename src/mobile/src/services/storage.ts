/**
 * Mobile Local Storage & Offline Cache Service
 * Enables instant feed loading and offline reading across regions with intermittent connectivity.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { Article } from '../types';

const STORAGE_KEYS = {
  ACTIVE_LANGUAGE: 'posipulse_active_lang',
  FEED_CACHE_PREFIX: 'posipulse_feed_cache_',
  THEME_MODE: 'posipulse_theme_mode',
};

export class MobileStorageService {
  /**
   * Save the user's active language preference.
   */
  async setActiveLanguage(code: string): Promise<void> {
    try {
      await AsyncStorage.setItem(STORAGE_KEYS.ACTIVE_LANGUAGE, code);
    } catch (e) {
      console.warn('Failed to persist active language:', e);
    }
  }

  /**
   * Get user's active language preference (defaults to 'en').
   */
  async getActiveLanguage(): Promise<string> {
    try {
      const lang = await AsyncStorage.getItem(STORAGE_KEYS.ACTIVE_LANGUAGE);
      return lang || 'en';
    } catch {
      return 'en';
    }
  }

  /**
   * Cache articles for offline reading. Capped at 50 per language.
   */
  async cacheArticles(language: string, articles: Article[]): Promise<void> {
    try {
      const key = `${STORAGE_KEYS.FEED_CACHE_PREFIX}${language}`;
      const payload = JSON.stringify(articles.slice(0, 50));
      await AsyncStorage.setItem(key, payload);
    } catch (e) {
      console.warn(`Failed to cache articles for ${language}:`, e);
    }
  }

  /**
   * Retrieve cached articles for offline reading when network is unreachable.
   */
  async getCachedArticles(language: string): Promise<Article[]> {
    try {
      const key = `${STORAGE_KEYS.FEED_CACHE_PREFIX}${language}`;
      const data = await AsyncStorage.getItem(key);
      return data ? (JSON.parse(data) as Article[]) : [];
    } catch {
      return [];
    }
  }
}

export const mobileStorage = new MobileStorageService();

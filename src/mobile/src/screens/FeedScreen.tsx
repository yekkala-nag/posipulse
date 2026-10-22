/**
 * Mobile Feed Screen
 * Main reader screen featuring pull-to-refresh, offline caching fallback,
 * category filtering, and bidirectional RTL rendering.
 */

import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  RefreshControl,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  SafeAreaView,
  StatusBar,
  ScrollView,
} from 'react-native';
import { Article, LanguageInfo } from '../types';
import { apiClient } from '../api/client';
import { mobileStorage } from '../services/storage';
import { ArticleCard } from '../components/ArticleCard';
import { LanguageSelector } from '../components/LanguageSelector';
import { FeedbackModal } from './FeedbackModal';

const VISIBLE_CATEGORIES = [
  { id: '', label: '✨ All' },
  { id: 'agriculture-rural', label: '🌾 Agriculture' },
  { id: 'science-technology', label: '🔬 Science & Tech' },
  { id: 'education-skills', label: '📚 Education' },
  { id: 'environment-climate', label: '🌱 Environment' },
  { id: 'sports', label: '🏆 Sports' },
  { id: 'society-community', label: '🤝 Community' },
  { id: 'arts-culture-heritage', label: '🎨 Arts & Culture' },
  { id: 'lifestyle-travel', label: '✈️ Lifestyle' },
  { id: 'economy-business', label: '📈 Economy' },
  { id: 'health-wellness', label: '🩺 Health' },
  { id: 'infrastructure-transport', label: '🚆 Infrastructure' },
  { id: 'entertainment-media', label: '🎭 Entertainment' },
  { id: 'world-diplomacy', label: '🌐 World' },
];

export const FeedScreen: React.FC = () => {
  const [languages, setLanguages] = useState<LanguageInfo[]>([]);
  const [currentLanguage, setCurrentLanguage] = useState<string>('en');
  const [currentCategory, setCurrentCategory] = useState<string>('');
  const [articles, setArticles] = useState<Article[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [reportingArticleId, setReportingArticleId] = useState<string | null>(null);

  const activeLangConfig = languages.find((l) => l.code === currentLanguage);
  const isRTL = Boolean(activeLangConfig?.is_rtl);

  // Initialize languages & active language
  useEffect(() => {
    async function init() {
      try {
        const langs = await apiClient.getLanguages();
        setLanguages(langs);
        const savedLang = await mobileStorage.getActiveLanguage();
        setCurrentLanguage(savedLang);
        loadFeed(savedLang, currentCategory);
      } catch (err) {
        console.warn('Network unavailable; loading cached feed');
        const savedLang = await mobileStorage.getActiveLanguage();
        const cached = await mobileStorage.getCachedArticles(savedLang);
        setArticles(cached);
        setLoading(false);
      }
    }
    init();
  }, []);

  const loadFeed = useCallback(
    async (lang: string, cat?: string) => {
      setLoading(true);
      try {
        const res = await apiClient.getFeed(lang, { category: cat || undefined });
        setArticles(res.articles);
        await mobileStorage.cacheArticles(lang, res.articles);
      } catch (err) {
        console.warn('Failed to fetch remote feed, loading cache:', err);
        const cached = await mobileStorage.getCachedArticles(lang);
        setArticles(cached);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    []
  );

  const handleSelectLanguage = async (code: string) => {
    setCurrentLanguage(code);
    await mobileStorage.setActiveLanguage(code);
    loadFeed(code, currentCategory);
  };

  const handleSelectCategory = (cat: string) => {
    const nextCat = currentCategory === cat ? '' : cat;
    setCurrentCategory(nextCat);
    loadFeed(currentLanguage, nextCat);
  };

  const onRefresh = () => {
    setRefreshing(true);
    loadFeed(currentLanguage, currentCategory);
  };

  const handleSeedDemo = async () => {
    try {
      setLoading(true);
      await apiClient.seedDemo(currentLanguage);
      await loadFeed(currentLanguage, currentCategory);
    } catch (err) {
      console.error('Demo seeding failed:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="light-content" backgroundColor="#0a0d14" />

      {/* Header */}
      <View style={styles.header}>
        <View style={styles.brandRow}>
          <Text style={styles.logoIcon}>🌱</Text>
          <Text style={styles.brandTitle}>PosiPulse</Text>
          <Text style={styles.brandTag}>शुद्ध समाचार</Text>
        </View>
        <Text style={styles.headerSubtitle}>
          Verified Constructive Journalism • English + 15 Indian Languages
        </Text>
      </View>

      {/* Language Selector */}
      <LanguageSelector
        languages={languages}
        selectedLanguage={currentLanguage}
        onSelectLanguage={handleSelectLanguage}
      />

      {/* Category Filter Pills (Horizontal Scroll Strip) */}
      <View style={styles.categoryBarContainer}>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.categoryScrollContent}
        >
          {VISIBLE_CATEGORIES.map((cat) => {
            const isActive = currentCategory === cat.id;
            return (
              <TouchableOpacity
                key={cat.id || 'all'}
                onPress={() => handleSelectCategory(cat.id)}
                style={[styles.categoryPill, isActive && styles.categoryPillActive]}
              >
                <Text style={[styles.categoryPillText, isActive && styles.categoryPillTextActive]}>
                  {cat.label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>

      {/* Main Content / Feed */}
      {loading && !refreshing ? (
        <View style={styles.centerContainer}>
          <ActivityIndicator color="#10b981" size="large" />
          <Text style={styles.loadingText}>Synthesizing constructive stories...</Text>
        </View>
      ) : articles.length === 0 ? (
        <View style={styles.centerContainer}>
          <Text style={styles.emptyIcon}>🌾</Text>
          <Text style={styles.emptyTitle}>No Stories in Current Filter</Text>
          <Text style={styles.emptySubtitle}>
            No constructive articles have been verified yet for this language or category.
          </Text>
          <TouchableOpacity style={styles.seedButton} onPress={handleSeedDemo}>
            <Text style={styles.seedButtonText}>⚡ Seed Verified Stories</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={articles}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <ArticleCard article={item} onReport={(id) => setReportingArticleId(id)} />
          )}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor="#10b981"
              colors={['#10b981']}
            />
          }
        />
      )}

      {/* DPDP Delist / Feedback Modal */}
      <FeedbackModal
        visible={Boolean(reportingArticleId)}
        articleId={reportingArticleId}
        onClose={() => setReportingArticleId(null)}
      />
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#0a0d14',
  },
  header: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 8,
    backgroundColor: '#0a0d14',
  },
  brandRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  logoIcon: {
    fontSize: 22,
  },
  brandTitle: {
    fontSize: 22,
    fontWeight: '800',
    color: '#f8fafc',
    letterSpacing: -0.5,
  },
  brandTag: {
    fontSize: 12,
    color: '#10b981',
    fontWeight: '700',
    backgroundColor: 'rgba(16, 185, 129, 0.15)',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  headerSubtitle: {
    fontSize: 11,
    color: '#64748b',
    marginTop: 4,
  },
  categoryBarContainer: {
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.05)',
  },
  categoryScrollContent: {
    paddingHorizontal: 16,
    gap: 8,
    flexDirection: 'row',
  },
  categoryPill: {
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderRadius: 16,
    backgroundColor: 'rgba(255, 255, 255, 0.06)',
  },
  categoryPillActive: {
    backgroundColor: '#38bdf8',
  },
  categoryPillText: {
    fontSize: 12,
    color: '#94a3b8',
    fontWeight: '600',
  },
  categoryPillTextActive: {
    color: '#0a0d14',
    fontWeight: '700',
  },
  listContent: {
    padding: 16,
  },
  centerContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  loadingText: {
    color: '#94a3b8',
    marginTop: 12,
    fontSize: 14,
  },
  emptyIcon: {
    fontSize: 48,
    marginBottom: 12,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#f8fafc',
    marginBottom: 6,
  },
  emptySubtitle: {
    fontSize: 13,
    color: '#94a3b8',
    textAlign: 'center',
    lineHeight: 18,
    marginBottom: 16,
  },
  seedButton: {
    backgroundColor: '#10b981',
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderRadius: 8,
  },
  seedButtonText: {
    color: '#0a0d14',
    fontWeight: '700',
    fontSize: 14,
  },
});

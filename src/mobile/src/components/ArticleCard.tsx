/**
 * Mobile Article Card Component
 * Highlights:
 * 1. Native headline & original-wording abstractive summary (zero raw publisher body).
 * 2. Substance-scaled length band indicator.
 * 3. Prominent publisher link-out button launching native in-app browser.
 * 4. Bi-directional layout for Perso-Arabic scripts (Urdu RTL).
 */

import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Article } from '../types';
import { SubstanceMeter } from './SubstanceMeter';
import { openPublisherStory } from '../utils/linking';

interface ArticleCardProps {
  article: Article;
  onReport: (articleId: string) => void;
}

export const ArticleCard: React.FC<ArticleCardProps> = ({ article, onReport }) => {
  const isRTL = Boolean(article.is_rtl);
  const wordCount = article.summary?.word_count || 50;
  const category = article.positivity?.category || 'General';

  const handleLinkOut = async () => {
    await openPublisherStory(article.canonical_url || article.url);
  };

  return (
    <View style={[styles.card, isRTL && styles.cardRTL]}>
      {/* Category + Entailment Verification Badge */}
      <View style={[styles.headerRow, isRTL && styles.headerRowRTL]}>
        <View style={styles.categoryBadge}>
          <Text style={styles.categoryText}>{category}</Text>
        </View>
        <View style={styles.verifiedBadge}>
          <Text style={styles.verifiedText}>✓ Verified Positive</Text>
        </View>
      </View>

      {/* Headline */}
      <Text style={[styles.headline, isRTL && styles.textRTL]}>
        {article.headline}
      </Text>

      {/* Substance Meter */}
      <SubstanceMeter wordCount={wordCount} isRTL={isRTL} />

      {/* Abstractive Original-Wording Summary Box */}
      <View style={styles.summaryContainer}>
        <View style={[styles.summaryBadgeRow, isRTL && styles.headerRowRTL]}>
          <Text style={styles.summaryBadge}>Original-Wording Synthesis</Text>
        </View>
        <Text style={[styles.summaryText, isRTL && styles.textRTL]}>
          {article.summary?.text}
        </Text>
      </View>

      {/* Prominent Original Publisher Link-Out Button */}
      <TouchableOpacity
        activeOpacity={0.8}
        onPress={handleLinkOut}
        style={[styles.publisherButton, isRTL && styles.publisherButtonRTL]}
      >
        <View style={[styles.publisherTextCol, isRTL && styles.publisherTextColRTL]}>
          <Text style={styles.publisherSubtext}>Read Full Story at</Text>
          <Text style={styles.publisherName}>{article.source_name || 'Original Publisher'}</Text>
        </View>
        <Text style={styles.arrowIcon}>↗</Text>
      </TouchableOpacity>

      {/* Footer / DPDP Safe Harbor Actions */}
      <View style={[styles.footerRow, isRTL && styles.headerRowRTL]}>
        <Text style={styles.dateText}>
          {article.published_at ? new Date(article.published_at).toLocaleDateString() : 'Recent'}
        </Text>
        <TouchableOpacity onPress={() => onReport(article.id)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
          <Text style={styles.reportText}>Report / DPDP</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#161e2e',
    borderRadius: 14,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
  },
  cardRTL: {
    direction: 'rtl',
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },
  headerRowRTL: {
    flexDirection: 'row-reverse',
  },
  categoryBadge: {
    backgroundColor: 'rgba(56, 189, 248, 0.15)',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: 'rgba(56, 189, 248, 0.3)',
  },
  categoryText: {
    color: '#38bdf8',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  verifiedBadge: {
    backgroundColor: 'rgba(16, 185, 129, 0.12)',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  verifiedText: {
    color: '#10b981',
    fontSize: 11,
    fontWeight: '600',
  },
  headline: {
    fontSize: 18,
    fontWeight: '700',
    color: '#f8fafc',
    lineHeight: 25,
  },
  textRTL: {
    textAlign: 'right',
    writingDirection: 'rtl',
  },
  summaryContainer: {
    backgroundColor: 'rgba(10, 13, 20, 0.55)',
    padding: 12,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.05)',
    marginVertical: 6,
  },
  summaryBadgeRow: {
    flexDirection: 'row',
    marginBottom: 6,
  },
  summaryBadge: {
    fontSize: 10,
    color: '#10b981',
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  summaryText: {
    fontSize: 14,
    color: '#cbd5e1',
    lineHeight: 22,
  },
  publisherButton: {
    backgroundColor: 'rgba(56, 189, 248, 0.1)',
    borderColor: 'rgba(56, 189, 248, 0.35)',
    borderWidth: 1,
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 14,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 12,
  },
  publisherButtonRTL: {
    flexDirection: 'row-reverse',
  },
  publisherTextCol: {
    flexDirection: 'column',
  },
  publisherTextColRTL: {
    alignItems: 'flex-end',
  },
  publisherSubtext: {
    fontSize: 11,
    color: '#94a3b8',
  },
  publisherName: {
    fontSize: 14,
    fontWeight: '700',
    color: '#38bdf8',
  },
  arrowIcon: {
    fontSize: 18,
    color: '#38bdf8',
    fontWeight: 'bold',
  },
  footerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 12,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255, 255, 255, 0.05)',
  },
  dateText: {
    fontSize: 12,
    color: '#64748b',
  },
  reportText: {
    fontSize: 12,
    color: '#ef4444',
    fontWeight: '600',
  },
});

/**
 * Mobile Horizontal Language Selector Pill Strip
 * Displays English + 15 Indian languages with native script rendering.
 */

import React from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet } from 'react-native';
import { LanguageInfo } from '../types';

interface LanguageSelectorProps {
  languages: LanguageInfo[];
  selectedLanguage: string;
  onSelectLanguage: (code: string) => void;
}

export const LanguageSelector: React.FC<LanguageSelectorProps> = ({
  languages,
  selectedLanguage,
  onSelectLanguage,
}) => {
  return (
    <View style={styles.wrapper}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
      >
        {languages.map((lang) => {
          const isSelected = lang.code === selectedLanguage;
          return (
            <TouchableOpacity
              key={lang.code}
              activeOpacity={0.7}
              onPress={() => onSelectLanguage(lang.code)}
              style={[styles.pill, isSelected && styles.pillActive]}
            >
              <Text style={[styles.nativeName, isSelected && styles.nativeNameActive]}>
                {lang.native_name}
              </Text>
              <View style={styles.metaRow}>
                <Text style={[styles.englishName, isSelected && styles.englishNameActive]}>
                  {lang.english_name}
                </Text>
                {lang.is_rtl && <Text style={styles.rtlBadge}>RTL</Text>}
              </View>
            </TouchableOpacity>
          );
        })}
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  wrapper: {
    backgroundColor: '#111622',
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.08)',
    paddingVertical: 10,
  },
  scrollContent: {
    paddingHorizontal: 16,
    gap: 8,
    flexDirection: 'row',
  },
  pill: {
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 20,
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  pillActive: {
    backgroundColor: 'rgba(16, 185, 129, 0.15)',
    borderColor: '#10b981',
  },
  nativeName: {
    fontSize: 14,
    fontWeight: '700',
    color: '#e2e8f0',
  },
  nativeNameActive: {
    color: '#10b981',
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 2,
  },
  englishName: {
    fontSize: 11,
    color: '#64748b',
  },
  englishNameActive: {
    color: '#94a3b8',
  },
  rtlBadge: {
    fontSize: 9,
    backgroundColor: 'rgba(245, 158, 11, 0.2)',
    color: '#f59e0b',
    paddingHorizontal: 3,
    paddingVertical: 1,
    borderRadius: 3,
    fontWeight: '700',
  },
});

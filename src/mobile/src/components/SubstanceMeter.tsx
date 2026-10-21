/**
 * Mobile Substance Meter Component
 * Visually communicates that summary length varies dynamically based on story substance.
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

interface SubstanceMeterProps {
  wordCount: number;
  isRTL?: boolean;
}

export const SubstanceMeter: React.FC<SubstanceMeterProps> = ({ wordCount, isRTL = false }) => {
  let tier = 'Compact';
  let activeBars = 1;
  let icon = '⚡';

  if (wordCount >= 75) {
    tier = 'Deep Dive';
    activeBars = 3;
    icon = '📚';
  } else if (wordCount >= 45) {
    tier = 'Balanced';
    activeBars = 2;
    icon = '⚖️';
  }

  return (
    <View style={[styles.container, isRTL && styles.containerRTL]}>
      <View style={[styles.tierRow, isRTL && styles.tierRowRTL]}>
        <Text style={styles.icon}>{icon}</Text>
        <Text style={styles.tierText}>Substance: {tier}</Text>
      </View>

      <View style={[styles.meterBars, isRTL && styles.meterBarsRTL]}>
        <View style={[styles.bar, activeBars >= 1 ? styles.barActive : styles.barInactive]} />
        <View style={[styles.bar, activeBars >= 2 ? styles.barActive : styles.barInactive]} />
        <View style={[styles.bar, activeBars >= 3 ? styles.barActive : styles.barInactive]} />
      </View>

      <View style={styles.badgeContainer}>
        <Text style={styles.badgeText}>{wordCount} words</Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.04)',
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 8,
    marginVertical: 10,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
  },
  containerRTL: {
    flexDirection: 'row-reverse',
  },
  tierRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginRight: 8,
  },
  tierRowRTL: {
    flexDirection: 'row-reverse',
    marginRight: 0,
    marginLeft: 8,
  },
  icon: {
    fontSize: 12,
    marginRight: 4,
  },
  tierText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#94a3b8',
  },
  meterBars: {
    flexDirection: 'row',
    alignItems: 'center',
    marginRight: 8,
    gap: 3,
  },
  meterBarsRTL: {
    flexDirection: 'row-reverse',
    marginRight: 0,
    marginLeft: 8,
  },
  bar: {
    width: 14,
    height: 5,
    borderRadius: 2,
  },
  barActive: {
    backgroundColor: '#10b981',
  },
  barInactive: {
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
  },
  badgeContainer: {
    marginLeft: 'auto',
    backgroundColor: 'rgba(56, 189, 248, 0.12)',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  badgeText: {
    fontSize: 11,
    color: '#38bdf8',
    fontWeight: '600',
  },
});

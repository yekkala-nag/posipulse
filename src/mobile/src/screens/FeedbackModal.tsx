/**
 * Mobile DPDP Delisting & Accuracy Feedback Modal
 * Fulfills India Digital Personal Data Protection (DPDP) Act 2023 compliance.
 */

import React, { useState } from 'react';
import {
  Modal,
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { apiClient } from '../api/client';

interface FeedbackModalProps {
  visible: boolean;
  articleId: string | null;
  onClose: () => void;
}

export const FeedbackModal: React.FC<FeedbackModalProps> = ({ visible, articleId, onClose }) => {
  const [feedbackType, setFeedbackType] = useState<string>('not_positive');
  const [comments, setComments] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);

  const handleSubmit = async () => {
    if (!articleId) return;
    if (!comments.trim()) {
      Alert.alert('Required', 'Please describe your concern.');
      return;
    }

    setLoading(true);
    try {
      await apiClient.submitFeedback({
        article_id: articleId,
        feedback_type: feedbackType as any,
        comments: comments.trim(),
      });
      Alert.alert('Report Received', 'Thank you. The safety auditor will review this story.');
      setComments('');
      onClose();
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Failed to submit report');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="slide">
      <View style={styles.overlay}>
        <View style={styles.container}>
          <Text style={styles.title}>Report Story / DPDP Inquiry</Text>
          <Text style={styles.subtitle}>
            PosiPulse enforces strictly constructive journalism and respects privacy delisting
            requests under the DPDP Act 2023.
          </Text>

          <Text style={styles.label}>Concern Type</Text>
          <View style={styles.typeSelector}>
            {[
              { id: 'not_positive', label: 'Not Constructive' },
              { id: 'toxic_positivity', label: 'Toxic Positivity' },
              { id: 'inaccurate_summary', label: 'Inaccurate Summary' },
              { id: 'broken_link', label: 'Broken Link' },
            ].map((item) => (
              <TouchableOpacity
                key={item.id}
                onPress={() => setFeedbackType(item.id)}
                style={[styles.typePill, feedbackType === item.id && styles.typePillActive]}
              >
                <Text
                  style={[
                    styles.typeText,
                    feedbackType === item.id && styles.typeTextActive,
                  ]}
                >
                  {item.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={styles.label}>Details</Text>
          <TextInput
            style={styles.textInput}
            multiline
            numberOfLines={4}
            placeholder="Explain why this article should be reviewed or delisted..."
            placeholderTextColor="#64748b"
            value={comments}
            onChangeText={setComments}
          />

          <View style={styles.buttonRow}>
            <TouchableOpacity style={styles.cancelBtn} onPress={onClose} disabled={loading}>
              <Text style={styles.cancelText}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.submitBtn} onPress={handleSubmit} disabled={loading}>
              {loading ? (
                <ActivityIndicator color="#fff" size="small" />
              ) : (
                <Text style={styles.submitText}>Submit Report</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.75)',
    justifyContent: 'center',
    padding: 20,
  },
  container: {
    backgroundColor: '#161e2e',
    borderRadius: 16,
    padding: 20,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.1)',
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
    color: '#f8fafc',
    marginBottom: 6,
  },
  subtitle: {
    fontSize: 13,
    color: '#94a3b8',
    lineHeight: 18,
    marginBottom: 16,
  },
  label: {
    fontSize: 13,
    fontWeight: '600',
    color: '#cbd5e1',
    marginBottom: 8,
  },
  typeSelector: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 16,
  },
  typePill: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 16,
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.1)',
  },
  typePillActive: {
    backgroundColor: 'rgba(239, 68, 68, 0.15)',
    borderColor: '#ef4444',
  },
  typeText: {
    fontSize: 12,
    color: '#94a3b8',
  },
  typeTextActive: {
    color: '#ef4444',
    fontWeight: '600',
  },
  textInput: {
    backgroundColor: '#0a0d14',
    borderRadius: 8,
    padding: 12,
    color: '#f8fafc',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.1)',
    textAlignVertical: 'top',
    fontSize: 14,
    height: 100,
    marginBottom: 20,
  },
  buttonRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 12,
  },
  cancelBtn: {
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 8,
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
  },
  cancelText: {
    color: '#94a3b8',
    fontWeight: '600',
    fontSize: 14,
  },
  submitBtn: {
    paddingVertical: 10,
    paddingHorizontal: 18,
    borderRadius: 8,
    backgroundColor: '#ef4444',
  },
  submitText: {
    color: '#fff',
    fontWeight: '700',
    fontSize: 14,
  },
});

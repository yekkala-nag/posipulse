/**
 * PosiPulse Mobile Application Entrypoint
 * Bootstraps the mobile feed reader for iOS and Android.
 */

import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { FeedScreen } from './src/screens/FeedScreen';

export default function App() {
  return (
    <>
      <StatusBar style="light" />
      <FeedScreen />
    </>
  );
}

/**
 * Mobile Publisher Link-Out Utility
 * Enforces prominent original publisher attribution without ad-stripping or scraping.
 * Automatically cleans tracking query parameters (e.g. utm_*) and launches
 * native in-app browser (SFSafariViewController on iOS, CustomTabs on Android).
 */

import { Linking, Platform } from 'react-native';

/**
 * Sanitizes target publisher URL by removing third-party tracking parameters.
 */
export function sanitizePublisherUrl(rawUrl: string): string {
  try {
    const url = new URL(rawUrl);
    const trackingParams = [
      'utm_source',
      'utm_medium',
      'utm_campaign',
      'utm_term',
      'utm_content',
      'fbclid',
      'gclid',
      '_ga',
    ];
    trackingParams.forEach((param) => url.searchParams.delete(param));
    return url.toString();
  } catch (err) {
    return rawUrl;
  }
}

/**
 * Opens publisher story in a native in-app browser view.
 * Respects publisher ads, paywalls, and cookie sessions.
 */
export async function openPublisherStory(url: string): Promise<boolean> {
  const cleanUrl = sanitizePublisherUrl(url);

  try {
    // Dynamic import of expo-web-browser if available
    let WebBrowser: any = null;
    try {
      WebBrowser = require('expo-web-browser');
    } catch {
      WebBrowser = null;
    }

    if (WebBrowser && typeof WebBrowser.openBrowserAsync === 'function') {
      await WebBrowser.openBrowserAsync(cleanUrl, {
        readerMode: false, // Respect publisher default design
        toolbarColor: '#0a0d14',
        controlsColor: '#10b981',
        enableBarCollapsing: true,
        showTitle: true,
      });
      return true;
    }

    // Fallback to standard system browser
    const supported = await Linking.canOpenURL(cleanUrl);
    if (supported) {
      await Linking.openURL(cleanUrl);
      return true;
    }
    return false;
  } catch (error) {
    console.error('Failed to open publisher link:', error);
    return false;
  }
}

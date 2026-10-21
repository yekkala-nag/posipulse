# ADR 0005: Mobile Client Architecture for iOS & Android

## Status
Accepted

## Context
The product requirement mandates a multi-platform application supporting Web, iOS, and Android across English and 15 Indian languages. The application presents constructive news with:
1. Headlines in the native script.
2. Abstractive original-wording summaries scaled to substance length bands (never storing or displaying raw publisher body text).
3. Prominent link-outs to original publishers on their sites or apps.
4. Support for 16 languages, including bidirectional right-to-left (RTL) layout for Perso-Arabic scripts (Urdu).
5. Fast, lightweight reading experience with offline caching and DPDP Act safe-harbor compliance.

We needed to determine the mobile architecture:
- Option A: Completely independent native apps (Swift/SwiftUI for iOS and Kotlin/Jetpack Compose for Android).
- Option B: Cross-platform unified mobile reader with React Native / Expo + TypeScript, supplemented by native platform integrations for deep-linking and in-app browser sessions.
- Option C: Web wrapper / PWA inside WebViews.

## Decision
We adopt **Option B** as the primary cross-platform mobile client architecture, supplemented by native iOS (SwiftUI) and Android (Jetpack Compose) platform views for reference and deep platform integrations.

### Rationale
1. **API Client & Model Sharing**: A single TypeScript/React Native codebase ensures that the OpenAPI 3.1 gateway client, pagination logic, offline caching, DPDP feedback submission, and data validation are identical across iOS and Android.
2. **Prominent Publisher Attribution via Native In-App Browsers**:
   - iOS uses `SFSafariViewController` / `ASWebAuthenticationSession` to open publisher stories directly in Safari's native context (preserving publisher cookies, logins, and reading modes while stripping tracking params).
   - Android uses `CustomTabsIntent` to open the publisher URL in Chrome/Default browser custom tabs.
   - This strictly fulfills the non-negotiable constraint: *"Always link out prominently. Never reproduce or store-for-display publisher article text."*
3. **Bi-Directional RTL & Multi-Script Typography**:
   - React Native's `I18nManager` combined with Android's `android:supportsRtl="true"` and iOS's semantic layout directions dynamically switches card flow, metadata alignment, and chevron directions when Urdu (`ur`) is selected.
   - Native font fallbacks render all 10 distinct Indic writing scripts without glyph clipping or conjunct corruption.
4. **Offline Resilience**:
   - Mobile client stores the latest 100 verified constructive stories per language locally in SQLite / AsyncStorage, enabling instant startup and offline reading in areas with intermittent connectivity across India.

## Consequences
- **Positive**: 90%+ code reuse between iOS and Android mobile platforms; zero drift in business logic or API contracts.
- **Positive**: Zero risk of displaying raw publisher body text on mobile.
- **Positive**: Native browser integration ensures publishers retain 100% of their ad impressions, analytics, and paywall protections upon user click-through.
- **Trade-off**: Requires bundling Noto Sans Indic font assets for legacy devices that lack built-in support for minority scripts (e.g. Ol Chiki, Maithili, or older Android builds).

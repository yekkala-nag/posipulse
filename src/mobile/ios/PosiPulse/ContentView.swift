//
//  ContentView.swift
//  PosiPulse iOS Reader
//  Native SwiftUI implementation supporting English + 15 Indian languages,
//  RTL layout for Urdu, substance meters, and prominent SFSafariViewController link-outs.
//

import SwiftUI
import SafariServices

// MARK: - Models
struct Article: Identifiable, Codable {
    let id: String
    let sourceId: String
    let sourceName: String
    let url: String
    let canonicalUrl: String
    let headline: String
    let publishedAt: String
    let language: String
    let isRtl: Bool?
    let positivity: PositivityMetadata
    let summary: SummaryMetadata

    enum CodingKeys: String, CodingKey {
        case id
        case sourceId = "source_id"
        case sourceName = "source_name"
        case url
        case canonicalUrl = "canonical_url"
        case headline
        case publishedAt = "published_at"
        case language
        case isRtl = "is_rtl"
        case positivity
        case summary
    }
}

struct PositivityMetadata: Codable {
    let label: String
    let score: Double
    let reason: String
    let category: String?
}

struct SummaryMetadata: Codable {
    let text: String
    let wordCount: Int
    let verified: Bool

    enum CodingKeys: String, CodingKey {
        case text
        case wordCount = "word_count"
        case verified
    }
}

// MARK: - Native Safari View for Prominent Publisher Attribution
struct SafariView: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context: Context) -> SFSafariViewController {
        let config = SFSafariViewController.Configuration()
        config.entersReaderIfAvailable = false // Respect publisher original presentation
        config.barCollapsingEnabled = true
        let vc = SFSafariViewController(url: url, configuration: config)
        vc.preferredBarTintColor = UIColor(red: 0.04, green: 0.05, blue: 0.08, alpha: 1.0)
        vc.preferredControlTintColor = UIColor(red: 0.06, green: 0.73, blue: 0.51, alpha: 1.0)
        return vc
    }

    func updateUIViewController(_ uiViewController: SFSafariViewController, context: Context) {}
}

// MARK: - Main SwiftUI Content View
struct ContentView: View {
    @State private var activeLanguage: String = "en"
    @State private var articles: [Article] = []
    @State private var selectedSafariUrl: URL? = nil
    @State private var isShowingSafari = false

    let languages = [
        ("en", "English", "English", false),
        ("hi", "Hindi", "हिन्दी", false),
        ("bn", "Bengali", "বাংলা", false),
        ("mr", "Marathi", "मराठी", false),
        ("te", "Telugu", "తెలుగు", false),
        ("ta", "Tamil", "தமிழ்", false),
        ("ur", "Urdu", "اردو", true),
        ("gu", "Gujarati", "ગુજરાતી", false),
        ("kn", "Kannada", "ಕನ್ನಡ", false),
        ("or", "Odia", "ଓଡ଼ିଆ", false),
        ("ml", "Malayalam", "മലയാളം", false),
        ("pa", "Punjabi", "ਪੰਜਾਬੀ", false),
        ("as", "Assamese", "অসমীয়া", false),
        ("ne", "Nepali", "नेपाली", false),
        ("mai", "Maithili", "मैथिली", false),
        ("gom", "Konkani", "कोंकणी", false),
    ]

    var isCurrentRtl: Bool {
        languages.first(where: { $0.0 == activeLanguage })?.3 ?? false
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color(red: 0.04, green: 0.05, blue: 0.08).ignoresSafeArea()

                VStack(spacing: 0) {
                    // Language Selector Pill Bar
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(languages, id: \.0) { code, engName, nativeName, rtl in
                                Button(action: { activeLanguage = code }) {
                                    VStack(spacing: 2) {
                                        Text(nativeName)
                                            .font(.system(size: 14, weight: .bold))
                                        HStack(spacing: 4) {
                                            Text(engName)
                                                .font(.system(size: 10))
                                            if rtl {
                                                Text("RTL")
                                                    .font(.system(size: 8, weight: .bold))
                                                    .padding(.horizontal, 3)
                                                    .background(Color.orange.opacity(0.3))
                                                    .cornerRadius(3)
                                            }
                                        }
                                    }
                                    .padding(.vertical, 8)
                                    .padding(.horizontal, 14)
                                    .background(activeLanguage == code ? Color.green.opacity(0.2) : Color.white.opacity(0.05))
                                    .foregroundColor(activeLanguage == code ? .green : .white)
                                    .cornerRadius(20)
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 20)
                                            .stroke(activeLanguage == code ? Color.green : Color.white.opacity(0.1), lineWidth: 1)
                                    )
                                }
                            }
                        }
                        .padding(.horizontal)
                        .padding(.vertical, 10)
                    }
                    .background(Color(red: 0.07, green: 0.09, blue: 0.13))

                    // Feed List
                    ScrollView {
                        LazyVStack(spacing: 16) {
                            ForEach(articles) { article in
                                ArticleCardView(article: article, onLinkOut: { url in
                                    selectedSafariUrl = url
                                    isShowingSafari = true
                                })
                            }
                        }
                        .padding()
                    }
                }
            }
            .navigationTitle("PosiPulse 🌱")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color(red: 0.04, green: 0.05, blue: 0.08), for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .sheet(isPresented: $isShowingSafari) {
                if let url = selectedSafariUrl {
                    SafariView(url: url)
                }
            }
            .environment(\.layoutDirection, isCurrentRtl ? .rightToLeft : .leftToRight)
        }
    }
}

// MARK: - Article Card View
struct ArticleCardView: View {
    let article: Article
    let onLinkOut: (URL) -> Void

    var substanceTier: (String, Int) {
        let count = article.summary.wordCount
        if count >= 75 { return ("Deep Dive", 3) }
        if count >= 45 { return ("Balanced", 2) }
        return ("Compact", 1)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Category & Verified Badge
            HStack {
                Text(article.positivity.category ?? "General")
                    .font(.caption)
                    .fontWeight(.bold)
                    .foregroundColor(.cyan)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.cyan.opacity(0.15))
                    .cornerRadius(6)

                Spacer()

                HStack(spacing: 4) {
                    Image(systemName: "checkmark.seal.fill")
                    Text("Verified Positive")
                }
                .font(.caption2)
                .foregroundColor(.green)
            }

            // Headline
            Text(article.headline)
                .font(.headline)
                .foregroundColor(.white)

            // Substance Length Band Bar
            HStack(spacing: 8) {
                Text("Substance: \(substanceTier.0)")
                    .font(.caption2)
                    .foregroundColor(.gray)

                HStack(spacing: 3) {
                    ForEach(1...3, id: \.self) { bar in
                        RoundedRectangle(cornerRadius: 2)
                            .fill(bar <= substanceTier.1 ? Color.green : Color.white.opacity(0.15))
                            .frame(width: 14, height: 4)
                    }
                }

                Spacer()

                Text("\(article.summary.wordCount) words")
                    .font(.caption2)
                    .foregroundColor(.cyan)
            }
            .padding(.vertical, 4)

            // Original-Wording Summary Box
            VStack(alignment: .leading, spacing: 6) {
                Text("ORIGINAL-WORDING SYNTHESIS")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundColor(.green)

                Text(article.summary.text)
                    .font(.subheadline)
                    .foregroundColor(Color(white: 0.85))
                    .lineSpacing(4)
            }
            .padding(10)
            .background(Color(red: 0.05, green: 0.06, blue: 0.09))
            .cornerRadius(8)

            // Prominent Publisher Link Button
            Button(action: {
                if let url = URL(string: article.canonicalUrl) {
                    onLinkOut(url)
                }
            }) {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Read Full Story at")
                            .font(.caption2)
                            .foregroundColor(.gray)
                        Text(article.sourceName)
                            .font(.subheadline)
                            .fontWeight(.bold)
                            .foregroundColor(.cyan)
                    }
                    Spacer()
                    Image(systemName: "arrow.up.right")
                        .foregroundColor(.cyan)
                }
                .padding(10)
                .background(Color.cyan.opacity(0.1))
                .cornerRadius(8)
            }
        }
        .padding()
        .background(Color(red: 0.09, green: 0.12, blue: 0.18))
        .cornerRadius(12)
    }
}

/**
 * PosiPulse Client Application Logic
 * Supports English + 15 Indian languages, Urdu RTL layout,
 * substance-scaled length band meters, and prominent publisher link-outs.
 */

document.addEventListener('DOMContentLoaded', () => {
  // State
  let currentLanguage = 'en';
  let currentCategory = '';
  let availableLanguages = [];
  let availableCategories = [];
  let categoriesById = {};
  let isRTL = false;

  // Anonymous Reader Identity & Following State (DPDP Compliant)
  let deviceId = getOrCreateDeviceId();
  let followedCategories = new Set();
  let followedSources = new Set();
  let isFollowingMode = false;

  // DOM Elements
  const languageStrip = document.getElementById('language-strip');
  const currentLangDisplay = document.getElementById('current-lang-display');
  const categoryFilters = document.getElementById('category-filters');
  const articlesGrid = document.getElementById('articles-grid');
  const emptyState = document.getElementById('empty-state');
  const feedResultsCounter = document.getElementById('feed-results-counter');
  const feedDirectionIndicator = document.getElementById('feed-direction-indicator');
  const seedDemoBtn = document.getElementById('seed-demo-btn');
  const emptySeedBtn = document.getElementById('empty-seed-btn');
  const fetchLiveBtn = document.getElementById('fetch-live-btn');
  const emptyLiveBtn = document.getElementById('empty-live-btn');
  const themeToggleBtn = document.getElementById('theme-toggle-btn');
  const themeIcon = document.getElementById('theme-icon');
  const feedbackModal = document.getElementById('feedback-modal');
  const modalCloseBtn = document.getElementById('modal-close-btn');
  const modalCancelBtn = document.getElementById('modal-cancel-btn');
  const feedbackForm = document.getElementById('feedback-form');
  const modalArticleId = document.getElementById('modal-article-id');

  // Following Management Elements
  const openFollowingBtn = document.getElementById('open-following-btn');
  const followingCountBadge = document.getElementById('following-count-badge');
  const followingModal = document.getElementById('following-modal');
  const followingCloseBtn = document.getElementById('following-close-btn');
  const followingDoneBtn = document.getElementById('following-done-btn');
  const clearAllFollowingBtn = document.getElementById('clear-all-following-btn');
  const followingCategoriesList = document.getElementById('following-categories-list');
  const followingSourcesList = document.getElementById('following-sources-list');

  // Initialize Theme & Following State
  initTheme();
  loadFollowingPreferences();

  function getOrCreateDeviceId() {
    let id = localStorage.getItem('posipulse_device_id');
    if (!id) {
      id = 'dev-' + Math.random().toString(36).substring(2, 12) + '-' + Date.now().toString(36);
      localStorage.setItem('posipulse_device_id', id);
    }
    return id;
  }

  async function loadFollowingPreferences() {
    try {
      const res = await fetch(`/v1/reader/${encodeURIComponent(deviceId)}/following`);
      if (res.ok) {
        const data = await res.json();
        followedCategories = new Set(data.categories || []);
        followedSources = new Set(data.sources || []);
        updateFollowingBadge();
      }
    } catch (err) {
      console.warn('Could not load following preferences:', err);
    }
  }

  function updateFollowingBadge() {
    const total = followedCategories.size + followedSources.size;
    if (followingCountBadge) {
      followingCountBadge.textContent = total;
    }
    const catFollowingPill = document.getElementById('cat-following-count');
    if (catFollowingPill) {
      catFollowingPill.textContent = `(${total})`;
    }
  }

  // Load Languages & Feed
  loadLanguages();

  // --------------------------------------------------------------------------
  // Theme Management
  // --------------------------------------------------------------------------
  function initTheme() {
    const savedTheme = localStorage.getItem('posipulse_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    themeIcon.textContent = savedTheme === 'dark' ? '🌙' : '☀️';

    themeToggleBtn.addEventListener('click', () => {
      const currentTheme = document.documentElement.getAttribute('data-theme');
      const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', newTheme);
      localStorage.setItem('posipulse_theme', newTheme);
      themeIcon.textContent = newTheme === 'dark' ? '🌙' : '☀️';
    });
  }

  // --------------------------------------------------------------------------
  // Language Registry & Navigation
  // --------------------------------------------------------------------------
  async function loadCategories(lang = currentLanguage) {
    try {
      const res = await fetch(`/v1/categories?language=${encodeURIComponent(lang)}`);
      if (!res.ok) throw new Error('Failed to fetch categories');
      const data = await res.json();
      availableCategories = data.categories || [];
      categoriesById = {};
      availableCategories.forEach((c) => {
        categoriesById[c.id] = c;
      });
      renderCategoryFilters();
    } catch (err) {
      console.warn('Falling back to default categories:', err);
    }
  }

  function renderCategoryFilters() {
    if (!categoryFilters) return;
    const isAllActive = !currentCategory && !isFollowingMode;
    const isFollowingActive = isFollowingMode;
    const totalFollowing = followedCategories.size + followedSources.size;
    let html = `
      <button class="filter-pill ${isAllActive ? 'active' : ''}" data-category="" id="cat-all">
        <span>✨</span> <span>All Stories</span>
      </button>
      <button class="filter-pill ${isFollowingActive ? 'active' : ''}" data-category="__following__" id="cat-following">
        <span>⭐</span> <span>Following <span id="cat-following-count">(${totalFollowing})</span></span>
      </button>
    `;

    availableCategories.forEach((cat) => {
      const isActive = !isFollowingMode && (currentCategory === cat.slug || currentCategory === String(cat.id));
      html += `
        <button class="filter-pill ${isActive ? 'active' : ''}" data-category="${cat.slug}" id="cat-${cat.slug}" title="${escapeHTML(cat.name_en)}">
          <span>${cat.icon}</span> <span>${escapeHTML(cat.display_name)}</span>
        </button>
      `;
    });

    categoryFilters.innerHTML = html;
  }

  async function loadLanguages() {
    try {
      const res = await fetch('/v1/languages');
      if (!res.ok) throw new Error('Failed to fetch languages');
      const data = await res.json();
      availableLanguages = data.languages || [];

      renderLanguageStrip();
      await loadCategories(currentLanguage);
      loadFeed();
    } catch (err) {
      console.error('Error loading languages:', err);
      // Fallback
      availableLanguages = [
        { code: 'en', english_name: 'English', native_name: 'English', is_rtl: false },
        { code: 'hi', english_name: 'Hindi', native_name: 'हिन्दी', is_rtl: false },
        { code: 'bn', english_name: 'Bengali', native_name: 'বাংলা', is_rtl: false },
        { code: 'mr', english_name: 'Marathi', native_name: 'मराठी', is_rtl: false },
        { code: 'te', english_name: 'Telugu', native_name: 'తెలుగు', is_rtl: false },
        { code: 'ta', english_name: 'Tamil', native_name: 'தமிழ்', is_rtl: false },
        { code: 'ur', english_name: 'Urdu', native_name: 'اردو', is_rtl: true },
        { code: 'gu', english_name: 'Gujarati', native_name: 'ગુજરાતી', is_rtl: false },
        { code: 'kn', english_name: 'Kannada', native_name: 'ಕನ್ನಡ', is_rtl: false },
        { code: 'or', english_name: 'Odia', native_name: 'ଓଡ଼ିଆ', is_rtl: false },
        { code: 'ml', english_name: 'Malayalam', native_name: 'മലയാളം', is_rtl: false },
        { code: 'pa', english_name: 'Punjabi', native_name: 'ਪੰਜਾਬੀ', is_rtl: false },
        { code: 'as', english_name: 'Assamese', native_name: 'অসমীয়া', is_rtl: false },
        { code: 'ne', english_name: 'Nepali', native_name: 'नेपाली', is_rtl: false },
        { code: 'mai', english_name: 'Maithili', native_name: 'मैथिली', is_rtl: false },
        { code: 'gom', english_name: 'Konkani', native_name: 'कोंकणी', is_rtl: false },
      ];
      renderLanguageStrip();
      await loadCategories(currentLanguage);
      loadFeed();
    }
  }

  function renderLanguageStrip() {
    languageStrip.innerHTML = '';

    availableLanguages.forEach((lang) => {
      const btn = document.createElement('button');
      btn.className = `lang-pill ${lang.code === currentLanguage ? 'active' : ''}`;
      btn.setAttribute('role', 'tab');
      btn.setAttribute('aria-selected', lang.code === currentLanguage ? 'true' : 'false');
      btn.setAttribute('id', `lang-tab-${lang.code}`);

      btn.innerHTML = `
        <span class="lang-pill-native">${lang.native_name}</span>
        <div class="lang-pill-meta">
          <span>${lang.english_name}</span>
          ${lang.is_rtl ? '<span class="rtl-mini-badge">RTL</span>' : ''}
        </div>
      `;

      btn.addEventListener('click', () => {
        if (currentLanguage === lang.code) return;
        selectLanguage(lang.code);
      });

      languageStrip.appendChild(btn);
    });
  }

  async function selectLanguage(code) {
    currentLanguage = code;
    const langObj = availableLanguages.find((l) => l.code === code);
    isRTL = langObj ? langObj.is_rtl : false;

    // Update active UI
    document.querySelectorAll('.lang-pill').forEach((el) => {
      el.classList.toggle('active', el.id === `lang-tab-${code}`);
      el.setAttribute('aria-selected', el.id === `lang-tab-${code}` ? 'true' : 'false');
    });

    currentLangDisplay.textContent = langObj
      ? `${langObj.english_name} (${langObj.code})${isRTL ? ' • RTL' : ''}`
      : code;

    // Update direction indicators
    feedDirectionIndicator.textContent = `Direction: ${isRTL ? 'RTL' : 'LTR'}`;
    feedDirectionIndicator.className = `direction-tag ${isRTL ? 'rtl-glow' : ''}`;

    // Dynamically refresh localized categories for new language
    await loadCategories(code);
    const nlSelect = document.getElementById('newsletter-lang-select');
    if (nlSelect) nlSelect.value = code;
    loadFeed();
  }

  // --------------------------------------------------------------------------
  // Category Filter Management
  // --------------------------------------------------------------------------
  categoryFilters.addEventListener('click', (e) => {
    const target = e.target.closest('.filter-pill');
    if (!target) return;

    document.querySelectorAll('.filter-pill').forEach((btn) => btn.classList.remove('active'));
    target.classList.add('active');

    const catAttr = target.getAttribute('data-category') || '';
    if (catAttr === '__following__') {
      isFollowingMode = true;
      currentCategory = '';
    } else {
      isFollowingMode = false;
      currentCategory = catAttr;
    }
    loadFeed();
  });

  const autoSeededLanguages = {};

  // --------------------------------------------------------------------------
  // Feed Loading & Rendering
  // --------------------------------------------------------------------------
  async function loadFeed() {
    renderSkeletons();
    emptyState.classList.add('hidden');

    try {
      let url;
      if (isFollowingMode) {
        url = `/v1/feed/following?device_id=${encodeURIComponent(deviceId)}&language=${encodeURIComponent(currentLanguage)}`;
      } else {
        url = `/v1/feed?language=${encodeURIComponent(currentLanguage)}`;
        if (currentCategory) {
          url += `&category=${encodeURIComponent(currentCategory)}`;
        }
      }

      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);

      const data = await res.json();
      let articles = data.articles || [];

      // Auto-seed demo stories on first visit to this language if feed is empty (not in following mode)
      if (articles.length === 0 && !currentCategory && !isFollowingMode && !autoSeededLanguages[currentLanguage]) {
        autoSeededLanguages[currentLanguage] = true;
        try {
          const seedRes = await fetch(`/v1/demo/seed?language=${encodeURIComponent(currentLanguage)}`, { method: 'POST' });
          if (seedRes.ok) {
            const retryRes = await fetch(url);
            if (retryRes.ok) {
              const retryData = await retryRes.json();
              articles = retryData.articles || [];
            }
          }
        } catch (seedErr) {
          console.warn('Auto-seed attempt failed:', seedErr);
        }
      }

      if (isFollowingMode) {
        feedResultsCounter.textContent = `Showing ${articles.length} stories from your followed topics & sources`;
      } else {
        feedResultsCounter.textContent = `Showing ${articles.length} verified constructive stories`;
      }

      if (articles.length === 0) {
        articlesGrid.innerHTML = '';
        if (isFollowingMode && (followedCategories.size + followedSources.size === 0)) {
          articlesGrid.innerHTML = `
            <div class="empty-state">
              <div class="empty-icon">⭐</div>
              <h3 class="empty-title">You Haven't Followed Any Topics or Sources Yet</h3>
              <p class="empty-description">Click "+ Follow" on any category or publisher card to tailor your constructive feed.</p>
            </div>
          `;
        } else {
          const emptyDesc = emptyState.querySelector('.empty-description');
          if (emptyDesc) {
            if (currentLanguage === 'gom' || currentLanguage === 'mai') {
              emptyDesc.textContent = 'PosiPulse upholds a strict ≥0.85 constructive threshold and fails closed. Because digital publishing in this language has lower online volume, fewer stories pass our editorial integrity checks without dilution. You can fetch live updates or seed verified demonstration items.';
            } else {
              emptyDesc.textContent = 'The pipeline fails closed to protect precision (≥0.85 positivity threshold). Fetch live stories directly from registered publisher RSS feeds or load verified demonstration items.';
            }
          }
          emptyState.classList.remove('hidden');
        }
      } else {
        renderArticles(articles);
      }
    } catch (err) {
      console.error('Failed to load feed:', err);
      articlesGrid.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">⚠️</div>
          <h3 class="empty-title">Unable to Load Stories</h3>
          <p class="empty-description">${err.message}</p>
        </div>
      `;
    }
  }

  function renderSkeletons() {
    articlesGrid.innerHTML = Array(4)
      .fill(0)
      .map(
        () => `
        <div class="skeleton-card">
          <div class="skeleton-line title"></div>
          <div class="skeleton-line subtitle"></div>
          <div class="skeleton-line"></div>
          <div class="skeleton-line" style="width: 60%;"></div>
        </div>
      `
      )
      .join('');
  }

  function renderArticles(articles) {
    articlesGrid.innerHTML = '';

    articles.forEach((art) => {
      const card = document.createElement('article');
      card.className = `article-card ${art.is_rtl ? 'is-rtl' : ''}`;
      if (art.is_rtl) {
        card.setAttribute('dir', 'rtl');
      }

      const pub = art.publisher_attribution || {};
      const rightsMode = pub.rights_mode || 'headline_only';
      const rightsModeLabel =
        rightsMode === 'longer_excerpt'
          ? 'Extended Excerpt'
          : rightsMode === 'feed_provided_excerpt'
          ? 'Feed Excerpt'
          : 'Headline Only';

      const faviconUrl = pub.favicon_url || (pub.primary_domain ? `https://${pub.primary_domain}/favicon.ico` : '');
      const directUrl = art.direct_url || art.canonical_url || art.url || '#';

      let categoryDisplay = art.positivity?.category || 'Constructive';
      let catClass = getCategoryClass(categoryDisplay);

      if (art.category && art.category.primary_id && categoriesById[art.category.primary_id]) {
        const catMeta = categoriesById[art.category.primary_id];
        categoryDisplay = `${catMeta.icon} ${catMeta.display_name}`;
        catClass = getCategoryClass(catMeta.slug);
      }

      // Substance calculation
      const wordCount = art.summary?.word_count || (art.summary?.text || '').split(/\s+/).length;
      const substanceInfo = getSubstanceInfo(wordCount);

      const publishedDate = art.published_at ? new Date(art.published_at).toLocaleDateString() : 'Recent';

      card.innerHTML = `
        <div>
          <!-- Publisher Attribution & Trust Header -->
          <div class="card-publisher-header">
            <div class="publisher-brand-info">
              ${faviconUrl ? `<img src="${escapeHTML(faviconUrl)}" class="publisher-favicon" alt="" onerror="this.style.display='none'">` : ''}
              <div class="publisher-brand-text">
                <span class="publisher-brand-title">${escapeHTML(pub.publisher_name || art.source_name || 'Publisher')}</span>
                ${pub.primary_domain ? `<span class="publisher-brand-domain">${escapeHTML(pub.primary_domain)}</span>` : ''}
              </div>
            </div>
            <div class="publisher-trust-badges">
              ${pub.verification_status === 'verified' ? `<span class="verified-domain-pill" title="Cryptographically verified publisher domain">✓ Verified Domain</span>` : ''}
              <span class="rights-mode-pill" title="Syndication Rights Mode">${escapeHTML(rightsModeLabel)}</span>
              ${art.source_id ? `
                <button class="follow-toggle-btn ${followedSources.has(art.source_id) ? 'active' : ''}" data-source-id="${escapeHTML(art.source_id)}" title="Follow / unfollow publisher source">
                  ${followedSources.has(art.source_id) ? '★ Following' : '+ Follow'}
                </button>
              ` : ''}
            </div>
          </div>

          <!-- Top Row: Category + Verified Badge -->
          <div class="card-top">
            <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
              <span class="category-tag ${catClass}">${escapeHTML(categoryDisplay)}</span>
              ${art.category && art.category.primary_id ? `
                <button class="follow-cat-btn ${followedCategories.has(art.category.primary_id) ? 'active' : ''}" data-cat-id="${art.category.primary_id}" title="Follow category">
                  ${followedCategories.has(art.category.primary_id) ? '★ Following' : '+ Follow'}
                </button>
              ` : ''}
            </div>
            <div class="card-meta-right">
              <span class="verified-badge" title="Faithfulness Verified Entailment Score">
                <span>✓</span> Verified Positive
              </span>
            </div>
          </div>

          <!-- Headline -->
          <h2 class="card-headline">${escapeHTML(art.headline)}</h2>

          <!-- Verbatim Publisher Excerpt (where terms allow) -->
          ${art.verbatim_excerpt ? `
            <div class="card-verbatim-box">
              <div class="verbatim-tag">
                <span>“ Publisher's Verbatim Excerpt</span>
                <span class="rights-mode-pill">${escapeHTML(rightsModeLabel)}</span>
              </div>
              <blockquote class="card-verbatim-text">${escapeHTML(art.verbatim_excerpt)}</blockquote>
            </div>
          ` : rightsMode === 'headline_only' ? `
            <div class="card-rights-note">
              <span>📰</span>
              <span>Headline-only rights agreement. Read complete reporting directly on ${escapeHTML(pub.publisher_name || art.source_name || 'the publisher\'s site')}.</span>
            </div>
          ` : ''}

          <!-- Substance Length Band Indicator -->
          <div class="substance-indicator-bar" title="Summary length dynamically scales with story factual substance">
            <div class="substance-label">
              <span>${substanceInfo.icon}</span>
              <span>Substance: ${substanceInfo.tier}</span>
            </div>
            <div class="substance-meter">
              <div class="meter-bar ${substanceInfo.bars >= 1 ? 'active' : ''}"></div>
              <div class="meter-bar ${substanceInfo.bars >= 2 ? 'active' : ''}"></div>
              <div class="meter-bar ${substanceInfo.bars >= 3 ? 'active' : ''}"></div>
            </div>
            <span class="word-count-badge">${wordCount} words</span>
          </div>

          <!-- Abstractive Summary Box (Original Words Only) -->
          ${art.summary?.text ? `
            <div class="card-summary-box">
              <span class="original-wording-tag">Original-Wording Synthesis</span>
              <p class="card-summary-text">${escapeHTML(art.summary.text)}</p>
            </div>
          ` : ''}
        </div>

        <!-- Bottom Actions & Prominent Direct Link-Out -->
        <div class="card-bottom">
          <a href="${escapeHTML(directUrl)}" target="_blank" rel="noopener noreferrer" class="publisher-link-btn" id="link-btn-${art.id}" data-article-id="${escapeHTML(art.id)}" data-source-id="${escapeHTML(art.source_id)}" data-lang="${escapeHTML(art.language)}" data-cat-id="${art.category?.primary_id || ''}">
            <div class="publisher-info">
              <span>Read Full Story at</span>
              <strong class="publisher-name">${escapeHTML(pub.publisher_name || art.source_name || 'Original Publisher')}</strong>
            </div>
            <span class="link-arrow">↗</span>
          </a>

          <div class="card-actions-row">
            <span>Published: ${publishedDate}</span>
            <button class="report-link" data-article-id="${art.id}">Report Story / DPDP</button>
          </div>
        </div>
      `;

      articlesGrid.appendChild(card);
    });

    // Attach follow/unfollow listeners for sources
    document.querySelectorAll('.follow-toggle-btn').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const sourceId = btn.getAttribute('data-source-id');
        if (!sourceId) return;
        const isFollowed = followedSources.has(sourceId);
        try {
          const res = await fetch(`/v1/reader/${encodeURIComponent(deviceId)}/follow`, {
            method: isFollowed ? 'DELETE' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ following_type: 'source', target_id: sourceId }),
          });
          if (!res.ok) throw new Error('Failed to update follow');
          if (isFollowed) {
            followedSources.delete(sourceId);
          } else {
            followedSources.add(sourceId);
          }
          updateFollowingBadge();
          renderCategoryFilters();
          if (isFollowingMode) {
            loadFeed();
          } else {
            document.querySelectorAll(`.follow-toggle-btn[data-source-id="${sourceId}"]`).forEach((b) => {
              b.classList.toggle('active', !isFollowed);
              b.textContent = !isFollowed ? '★ Following' : '+ Follow';
            });
          }
        } catch (err) {
          console.error('Follow error:', err);
        }
      });
    });

    // Attach follow/unfollow listeners for categories
    document.querySelectorAll('.follow-cat-btn').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const catIdStr = btn.getAttribute('data-cat-id');
        if (!catIdStr) return;
        const catId = parseInt(catIdStr, 10);
        const isFollowed = followedCategories.has(catId);
        try {
          const res = await fetch(`/v1/reader/${encodeURIComponent(deviceId)}/follow`, {
            method: isFollowed ? 'DELETE' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ following_type: 'category', target_id: catId }),
          });
          if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || 'Failed to update follow');
          }
          if (isFollowed) {
            followedCategories.delete(catId);
          } else {
            followedCategories.add(catId);
          }
          updateFollowingBadge();
          renderCategoryFilters();
          if (isFollowingMode) {
            loadFeed();
          } else {
            document.querySelectorAll(`.follow-cat-btn[data-cat-id="${catId}"]`).forEach((b) => {
              b.classList.toggle('active', !isFollowed);
              b.textContent = !isFollowed ? '★ Following' : '+ Follow';
            });
          }
        } catch (err) {
          console.error('Category follow error:', err);
          alert(err.message);
        }
      });
    });

    // Attach anonymous click analytics tracking to publisher link-out buttons
    document.querySelectorAll('.publisher-link-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const artId = btn.getAttribute('data-article-id');
        const srcId = btn.getAttribute('data-source-id');
        const lang = btn.getAttribute('data-lang');
        const catId = btn.getAttribute('data-cat-id');
        if (artId && srcId) {
          fetch('/v1/analytics/click', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              article_id: artId,
              source_id: srcId,
              language: lang || 'en',
              category_id: catId ? parseInt(catId, 10) : null,
            }),
          }).catch(() => {});
        }
      });
    });

    // Attach report button listeners
    document.querySelectorAll('.report-link').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        const id = e.target.getAttribute('data-article-id');
        openFeedbackModal(id);
      });
    });
  }

  function getCategoryClass(category) {
    const lower = (category || '').toLowerCase();
    if (lower.includes('agri') || lower.includes('rural')) return 'agriculture';
    if (lower.includes('science') || lower.includes('tech')) return 'science-tech';
    if (lower.includes('edu') || lower.includes('skill')) return 'education';
    if (lower.includes('ecolog') || lower.includes('climate') || lower.includes('nature') || lower.includes('environment')) return 'ecology';
    if (lower.includes('sport')) return 'sports';
    if (lower.includes('societ') || lower.includes('communit') || lower.includes('empower')) return 'community';
    if (lower.includes('art') || lower.includes('culture') || lower.includes('heritage')) return 'arts';
    if (lower.includes('life') || lower.includes('travel')) return 'lifestyle';
    if (lower.includes('econ') || lower.includes('business')) return 'economy';
    if (lower.includes('health') || lower.includes('wellness')) return 'health';
    if (lower.includes('infra') || lower.includes('transport')) return 'infrastructure';
    if (lower.includes('entertain') || lower.includes('media') || lower.includes('film') || lower.includes('music')) return 'entertainment';
    if (lower.includes('world') || lower.includes('diplo')) return 'world';
    if (lower.includes('civic')) return 'civic';
    return 'science-tech';
  }

  function getSubstanceInfo(wordCount) {
    if (wordCount <= 38) {
      return { tier: 'Compact', icon: '🔹', bars: 1 };
    } else if (wordCount <= 60) {
      return { tier: 'Balanced', icon: '🔷', bars: 2 };
    } else {
      return { tier: 'Deep Dive', icon: '💠', bars: 3 };
    }
  }

  function escapeHTML(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // --------------------------------------------------------------------------
  // Demo Seeding Integration
  // --------------------------------------------------------------------------
  async function seedDemoStories() {
    seedDemoBtn.disabled = true;
    seedDemoBtn.innerHTML = '<span>⏳ Processing...</span>';

    try {
      const res = await fetch(`/v1/demo/seed?language=${encodeURIComponent(currentLanguage)}`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error('Seeding endpoint returned error');
      const result = await res.json();
      console.log('Seeded items:', result);
      await loadFeed();
    } catch (err) {
      console.error('Seeding failed:', err);
      alert(`Could not seed items for ${currentLanguage}: ${err.message}`);
    } finally {
      seedDemoBtn.disabled = false;
      seedDemoBtn.innerHTML = '<span class="btn-icon">⚡</span> Seed Demo Stories';
    }
  }

  seedDemoBtn.addEventListener('click', seedDemoStories);
  emptySeedBtn.addEventListener('click', seedDemoStories);

  async function fetchLiveNews() {
    if (fetchLiveBtn) {
      fetchLiveBtn.disabled = true;
      fetchLiveBtn.innerHTML = '<span class="btn-icon">⏳</span> Fetching Live...';
    }
    if (emptyLiveBtn) {
      emptyLiveBtn.disabled = true;
      emptyLiveBtn.innerHTML = '<span class="btn-icon">⏳</span> Fetching Live...';
    }

    try {
      const res = await fetch(`/v1/ingest/live?language=${encodeURIComponent(currentLanguage)}&force=true`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error(`Live ingest error: HTTP ${res.status}`);
      const data = await res.json();
      console.log('Live ingest result:', data);
      await loadFeed();
    } catch (err) {
      console.error('Dynamic fetch failed:', err);
      alert(`Could not fetch live news for ${currentLanguage}: ${err.message}`);
    } finally {
      if (fetchLiveBtn) {
        fetchLiveBtn.disabled = false;
        fetchLiveBtn.innerHTML = '<span class="btn-icon">🔄</span> Fetch Live News';
      }
      if (emptyLiveBtn) {
        emptyLiveBtn.disabled = false;
        emptyLiveBtn.innerHTML = '<span class="btn-icon">🔄</span> Fetch Live News';
      }
    }
  }

  if (fetchLiveBtn) fetchLiveBtn.addEventListener('click', fetchLiveNews);
  if (emptyLiveBtn) emptyLiveBtn.addEventListener('click', fetchLiveNews);

  // --------------------------------------------------------------------------
  // Feedback & DPDP Delisting Modal
  // --------------------------------------------------------------------------
  function openFeedbackModal(articleId) {
    modalArticleId.value = articleId;
    feedbackModal.classList.remove('hidden');
  }

  function closeFeedbackModal() {
    feedbackModal.classList.add('hidden');
    feedbackForm.reset();
  }

  modalCloseBtn.addEventListener('click', closeFeedbackModal);
  modalCancelBtn.addEventListener('click', closeFeedbackModal);

  feedbackForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const articleId = modalArticleId.value;
    const feedbackType = document.getElementById('feedback-type').value;
    const comments = document.getElementById('feedback-comments').value;

    try {
      const res = await fetch('/v1/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          article_id: articleId,
          feedback_type: feedbackType,
          comments: comments,
        }),
      });

      if (!res.ok) throw new Error('Failed to submit report');
      alert('Thank you! Your feedback has been recorded and will be reviewed by the safety auditor.');
      closeFeedbackModal();
    } catch (err) {
      alert(`Error submitting feedback: ${err.message}`);
    }
  });

  // --------------------------------------------------------------------------
  // Reader Following Modal Management (DPDP Act 2023 Compliant)
  // --------------------------------------------------------------------------
  function openFollowingModal() {
    renderFollowingModalLists();
    if (followingModal) followingModal.classList.remove('hidden');
  }

  function closeFollowingModal() {
    if (followingModal) followingModal.classList.add('hidden');
  }

  function renderFollowingModalLists() {
    if (!followingCategoriesList || !followingSourcesList) return;

    // Render followed categories
    if (followedCategories.size === 0) {
      followingCategoriesList.innerHTML = '<span class="empty-following-msg" style="color: var(--text-muted); font-size: 0.85rem;">No categories followed yet.</span>';
    } else {
      followingCategoriesList.innerHTML = Array.from(followedCategories)
        .map((catId) => {
          const meta = categoriesById[catId] || { display_name: `Category ${catId}`, icon: '🏷️' };
          return `
            <span class="following-item-chip" style="display: inline-flex; align-items: center; gap: 0.4rem; background: var(--bg-surface-elevated, #2a2a2a); border: 1px solid var(--border-color); padding: 0.3rem 0.6rem; border-radius: 9999px; font-size: 0.85rem;">
              <span>${meta.icon || '🏷️'} ${escapeHTML(meta.display_name)}</span>
              <button class="remove-chip-btn" data-cat-id="${catId}" style="background: none; border: none; cursor: pointer; color: var(--text-muted); font-weight: bold; padding: 0 2px;" title="Unfollow">✕</button>
            </span>
          `;
        })
        .join('');
    }

    // Render followed sources
    if (followedSources.size === 0) {
      followingSourcesList.innerHTML = '<span class="empty-following-msg" style="color: var(--text-muted); font-size: 0.85rem;">No publisher sources followed yet.</span>';
    } else {
      followingSourcesList.innerHTML = Array.from(followedSources)
        .map((srcId) => {
          return `
            <span class="following-item-chip" style="display: inline-flex; align-items: center; gap: 0.4rem; background: var(--bg-surface-elevated, #2a2a2a); border: 1px solid var(--border-color); padding: 0.3rem 0.6rem; border-radius: 9999px; font-size: 0.85rem;">
              <span>📰 ${escapeHTML(srcId)}</span>
              <button class="remove-chip-btn" data-source-id="${escapeHTML(srcId)}" style="background: none; border: none; cursor: pointer; color: var(--text-muted); font-weight: bold; padding: 0 2px;" title="Unfollow">✕</button>
            </span>
          `;
        })
        .join('');
    }

    // Attach chip remove handlers
    followingCategoriesList.querySelectorAll('.remove-chip-btn').forEach((b) => {
      b.addEventListener('click', async () => {
        const catId = parseInt(b.getAttribute('data-cat-id'), 10);
        await unfollowItem('category', catId);
        followedCategories.delete(catId);
        updateFollowingBadge();
        renderFollowingModalLists();
        renderCategoryFilters();
        if (isFollowingMode) loadFeed();
      });
    });

    followingSourcesList.querySelectorAll('.remove-chip-btn').forEach((b) => {
      b.addEventListener('click', async () => {
        const srcId = b.getAttribute('data-source-id');
        await unfollowItem('source', srcId);
        followedSources.delete(srcId);
        updateFollowingBadge();
        renderFollowingModalLists();
        renderCategoryFilters();
        if (isFollowingMode) loadFeed();
      });
    });
  }

  async function unfollowItem(type, targetId) {
    try {
      await fetch(`/v1/reader/${encodeURIComponent(deviceId)}/follow`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ following_type: type, target_id: targetId }),
      });
    } catch (err) {
      console.warn('Unfollow failed:', err);
    }
  }

  async function clearAllFollowingData() {
    if (!confirm('DPDP Erasure: Are you sure you want to permanently delete all stored following preferences? This action cannot be undone.')) {
      return;
    }
    try {
      const res = await fetch(`/v1/reader/${encodeURIComponent(deviceId)}/following`, {
        method: 'DELETE',
      });
      if (res.ok) {
        followedCategories.clear();
        followedSources.clear();
        updateFollowingBadge();
        renderFollowingModalLists();
        renderCategoryFilters();
        if (isFollowingMode) loadFeed();
        alert('All reader preferences have been permanently erased from the server.');
      }
    } catch (err) {
      alert(`Could not erase data: ${err.message}`);
    }
  }

  if (openFollowingBtn) openFollowingBtn.addEventListener('click', openFollowingModal);
  if (followingCloseBtn) followingCloseBtn.addEventListener('click', closeFollowingModal);
  if (followingDoneBtn) followingDoneBtn.addEventListener('click', closeFollowingModal);
  if (clearAllFollowingBtn) clearAllFollowingBtn.addEventListener('click', clearAllFollowingData);

  // --------------------------------------------------------------------------
  // Newsletter Signup Integration (Double Opt-In & DPDP Compliant)
  // --------------------------------------------------------------------------
  const newsletterForm = document.getElementById('newsletter-form');
  const newsletterEmail = document.getElementById('newsletter-email');
  const newsletterLangSelect = document.getElementById('newsletter-lang-select');
  const newsletterFeedback = document.getElementById('newsletter-feedback');
  const newsletterSubmitBtn = document.getElementById('newsletter-submit-btn');

  if (newsletterForm) {
    newsletterForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = (newsletterEmail.value || '').trim();
      const lang = newsletterLangSelect ? newsletterLangSelect.value : currentLanguage;

      if (!email) return;

      newsletterSubmitBtn.disabled = true;
      newsletterSubmitBtn.innerHTML = '<span>⏳ Sending...</span>';
      newsletterFeedback.className = 'newsletter-feedback hidden';

      try {
        const res = await fetch('/v1/newsletter/subscribe', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: email, language: lang }),
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Subscription request failed.');

        newsletterFeedback.textContent = '✨ Verification link sent! Please check your inbox to confirm your subscription (Double Opt-In).';
        newsletterFeedback.className = 'newsletter-feedback success';
        newsletterEmail.value = '';
      } catch (err) {
        newsletterFeedback.textContent = `⚠️ ${err.message}`;
        newsletterFeedback.className = 'newsletter-feedback error';
      } finally {
        newsletterSubmitBtn.disabled = false;
        newsletterSubmitBtn.innerHTML = '<span>Subscribe ↗</span>';
      }
    });
  }
});

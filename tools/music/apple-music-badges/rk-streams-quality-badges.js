/**
 * RKplex music UI — quality from real audio streams + cleaned titles.
 * Lossless / Hi-Res Lossless marks are inline SVG (not Apple CDN / logo.png).
 */
(function () {
  const STYLE_ID = "rk-music-streams-ui";
  const QUALITY_RE = /\s*\[(?:Hi-Res\s*Lossless|Hi-Res|Lossless)\]\s*/gi;

  const css = `
  .detailLogo,
  img.detailLogo,
  .itemDetailPage .detailLogo,
  .itemDetailPage img[src*="/Images/Logo"] {
    display: none !important;
    height: 0 !important; width: 0 !important; opacity: 0 !important;
  }
  .rk-qmark {
    display: inline-flex;
    align-items: center;
    gap: .4rem;
    height: 22px;
    padding: 0 .55rem 0 .4rem;
    border-radius: 999px;
    background: rgba(255,255,255,.12);
    border: 1px solid rgba(255,255,255,.22);
    color: #fff;
    font: 600 11px/1 -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
    letter-spacing: .01em;
    vertical-align: middle;
    margin: .4rem .25rem .1rem 0;
    white-space: nowrap;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
  }
  .rk-qmark svg { width: 16px; height: 14px; display: block; flex: 0 0 auto; }
  .rk-qmark .rk-qmark-text { display: flex; flex-direction: column; justify-content: center; line-height: 1.05; }
  .rk-qmark.rk-qmark-hires .rk-qmark-text { font-size: 9px; font-weight: 700; }
  .detailPagePrimaryContainer .rk-qmark { height: 26px; font-size: 12px; margin-top: .55rem; }
  .detailPagePrimaryContainer .rk-qmark.rk-qmark-hires .rk-qmark-text { font-size: 10px; }
  .detailPagePrimaryContainer .rk-qmark svg { width: 18px; height: 16px; }
  .cardBox .rk-qmark {
    position: absolute; left: .35rem; bottom: .35rem; z-index: 6;
    height: 18px; font-size: 9px; margin: 0; padding: 0 .4rem 0 .3rem;
  }
  .cardBox .rk-qmark svg { width: 12px; height: 11px; }
  .nowPlayingBar .rk-qmark, .appfooter .rk-qmark {
    height: 16px; font-size: 9px; margin: 0 0 0 .4rem; padding: 0 .4rem 0 .3rem;
  }
  .rk-music-backdrop {
    position: absolute !important; inset: 0; z-index: 0; pointer-events: none; overflow: hidden;
  }
  .rk-music-backdrop img {
    width: 100%; height: 100%; object-fit: cover;
    filter: blur(48px) saturate(1.3) brightness(.5); transform: scale(1.2); opacity: .95;
  }
  .rk-music-backdrop::after {
    content: ""; position: absolute; inset: 0;
    background: linear-gradient(180deg, rgba(0,0,0,.2), rgba(0,0,0,.55) 40%, rgba(0,0,0,.92));
  }
  .itemDetailPage.rk-music-page .detailPagePrimaryContainer { position: relative; overflow: hidden; }
  .itemDetailPage.rk-music-page .detailPagePrimaryContainer > *:not(.rk-music-backdrop),
  .itemDetailPage.rk-music-page .detailPageContent { position: relative; z-index: 1; }
  `;

  function ensureStyle() {
    let el = document.getElementById(STYLE_ID);
    if (!el) {
      el = document.createElement("style");
      el.id = STYLE_ID;
      document.head.appendChild(el);
    }
    el.textContent = css;
  }

  function waveSvg() {
    return `<svg viewBox="0 0 24 18" aria-hidden="true"><path fill="currentColor" d="M1.5 9c2-4 4-4 6 0s4 4 6 0 4-4 6 0" opacity=".35"/><path fill="currentColor" d="M1.5 9c2-5.5 4-5.5 6 0s4 5.5 6 0 4-5.5 6 0"/><path fill="currentColor" d="M1.5 9c2-2.8 4-2.8 6 0s4 2.8 6 0 4-2.8 6 0" opacity=".55"/></svg>`;
  }

  function makeBadge(kind) {
    const el = document.createElement("span");
    el.className = "rk-qmark rk-quality-mark" + (kind === "lossless" ? "" : " rk-qmark-hires");
    el.dataset.rkKind = kind;
    if (kind === "lossless") {
      el.innerHTML = waveSvg() + `<span class="rk-qmark-text">Lossless</span>`;
      el.title = "Lossless";
    } else {
      el.innerHTML = waveSvg() + `<span class="rk-qmark-text"><span>Hi-Res</span><span>Lossless</span></span>`;
      el.title = "Hi-Res Lossless";
    }
    return el;
  }

  function qualityFromStreams(streams) {
    if (!streams || !streams.length) return null;
    const a = streams.find((s) => (s.Type || s.type) === "Audio") || streams[0];
    if (!a) return null;
    const bits = Number(a.BitDepth || a.bitDepth || 0);
    const rate = Number(a.SampleRate || a.sampleRate || 0);
    const codec = String(a.Codec || a.codec || "").toLowerCase();
    const lossless = /flac|alac|pcm|wav|aiff|dsd/.test(codec) || bits >= 16;
    if (bits >= 24 && rate > 48000) return "hires_lossless";
    if (bits >= 24 || rate > 48000) return "hires_lossless";
    if (lossless || bits >= 16) return "lossless";
    return null;
  }

  function qualityFromText(text) {
    const t = (text || "").toLowerCase();
    if (t.includes("hi-res lossless") || t.includes("hires lossless")) return "hires_lossless";
    if (t.includes("[hi-res]") || /\bhi-?res\b/.test(t)) return "hires_lossless";
    if (t.includes("lossless") || /\bflac\b/.test(t)) return "lossless";
    return null;
  }

  function cleanText(el) {
    if (!el || el.dataset.rkCleaned === "1") return;
    const raw = (el.textContent || "").trim();
    if (!QUALITY_RE.test(raw)) return;
    QUALITY_RE.lastIndex = 0;
    el.dataset.rkCleaned = "1";
    el.dataset.rkOriginal = raw;
    el.setAttribute("title", raw);
    el.textContent = raw.replace(QUALITY_RE, " ").replace(/\s{2,}/g, " ").trim();
  }

  function upsert(host, kind) {
    if (!host || !kind) return;
    let mark = host.querySelector(":scope > .rk-quality-mark");
    if (!mark) {
      host.appendChild(makeBadge(kind));
      return;
    }
    if (mark.dataset.rkKind !== kind) {
      mark.replaceWith(makeBadge(kind));
    }
  }

  function enhanceBackdrop(page) {
    page.classList.add("rk-music-page");
    if (page.querySelector(".rk-music-backdrop")) return;
    const cover =
      page.querySelector(".detailImageContainer img, .detailPortrait img, .itemPrimaryImage img") ||
      page.querySelector("img.itemDetailImage, img.detailImage");
    if (!cover || !cover.src) return;
    const wrap = document.createElement("div");
    wrap.className = "rk-music-backdrop";
    const img = document.createElement("img");
    img.alt = "";
    img.src = cover.src;
    wrap.appendChild(img);
    const host = page.querySelector(".detailPagePrimaryContainer") || page;
    host.style.position = host.style.position || "relative";
    host.insertBefore(wrap, host.firstChild);
  }

  async function fetchItem(itemId) {
    try {
      if (!window.ApiClient || !itemId) return null;
      const uid = ApiClient.getCurrentUserId();
      return await ApiClient.getItem(uid, itemId);
    } catch (e) {
      return null;
    }
  }

  function itemIdFromLocation() {
    const m = (location.hash || "").match(/id=([a-f0-9]+)/i);
    return m ? m[1] : null;
  }

  async function decorateDetail() {
    const page = document.querySelector(".itemDetailPage");
    if (!page) return;
    enhanceBackdrop(page);
    page.querySelectorAll(".detailLogo, img[src*=\"/Images/Logo\"]").forEach((n) => n.remove());

    const title =
      page.querySelector(".itemName.originalTitle, .nameContainer .itemName, h1.itemName, .itemName") ||
      page.querySelector(".detailPagePrimaryContainer .itemName");
    if (!title) return;
    cleanText(title);

    let kind = qualityFromText((title.dataset.rkOriginal || title.textContent) + " " + document.title);
    const iid = itemIdFromLocation();
    if (iid) {
      const item = await fetchItem(iid);
      if (item) {
        // Album: sample first child audio if needed
        let streams = item.MediaStreams;
        if ((!streams || !streams.length) && item.Type === "MusicAlbum") {
          try {
            const kids = await ApiClient.getItems(ApiClient.getCurrentUserId(), {
              ParentId: iid,
              IncludeItemTypes: "Audio",
              Recursive: true,
              Limit: 1,
              Fields: "MediaStreams",
            });
            const first = (kids.Items || [])[0];
            streams = first && first.MediaStreams;
          } catch (e) {}
        }
        kind = qualityFromStreams(streams) || kind;
      }
    }

    if (!kind) return;
    let row = page.querySelector(".rk-qmark-row");
    if (!row) {
      row = document.createElement("div");
      row.className = "rk-qmark-row";
      (title.parentElement || title).insertBefore(row, title.nextSibling);
    }
    upsert(row, kind);
  }

  function currentPlayingItem() {
    try {
      const pm = window.PlaybackManager || window.playbackManager;
      if (pm && typeof pm.currentItem === "function") return pm.currentItem();
      if (pm && pm._currentItem) return pm._currentItem;
    } catch (e) {}
    return null;
  }

  async function decorateNowPlaying() {
    const secondary =
      document.querySelector(".nowPlayingBarSecondaryText") ||
      document.querySelector(".nowPlayingBarInfo .secondaryText") ||
      document.querySelector(".nowPlayingBarText");
    if (secondary) cleanText(secondary);

    let kind = qualityFromText(
      [(secondary && (secondary.dataset.rkOriginal || secondary.textContent)), document.title].filter(Boolean).join(" ")
    );

    const item = currentPlayingItem();
    if (item) {
      let streams = item.MediaStreams;
      if (!streams && item.Id) {
        const full = await fetchItem(item.Id);
        streams = full && full.MediaStreams;
      }
      kind = qualityFromStreams(streams) || kind;
    }

    if (!kind || !secondary) return;
    const host = secondary.parentElement || secondary;
    upsert(host, kind);
  }

  function decorateCards(root) {
    root.querySelectorAll(".card, .cardBox").forEach((card) => {
      if (card.querySelector(".rk-quality-mark")) return;
      const parts = [];
      card.querySelectorAll(".cardText, .cardText-first, .cardText-secondary").forEach((n) => {
        parts.push(n.textContent || "");
        cleanText(n);
      });
      const kind = qualityFromText(parts.join(" ") + " " + (card.getAttribute("title") || ""));
      if (!kind) return;
      const host = card.classList.contains("cardBox") ? card : card.querySelector(".cardBox") || card;
      host.style.position = host.style.position || "relative";
      host.appendChild(makeBadge(kind));
    });
  }

  let busy = false;
  async function run() {
    if (busy) return;
    busy = true;
    try {
      ensureStyle();
      decorateCards(document);
      await decorateDetail();
      await decorateNowPlaying();
    } finally {
      busy = false;
    }
  }

  ensureStyle();
  run();
  const obs = new MutationObserver(() => run());
  obs.observe(document.documentElement, { childList: true, subtree: true });
  setInterval(run, 2500);
  window.addEventListener("hashchange", () => setTimeout(run, 250));
  document.addEventListener("viewshow", () => setTimeout(run, 250));
})();

// HTTP helpers and media lookups for the control panel.

export async function api(method, path, data) {
  const init = { method, headers: {} };
  if (data instanceof FormData) {
    init.body = data;
  } else if (data != null) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(data);
  }
  const r = await fetch(path, init);
  const type = r.headers.get('content-type') || '';
  const body = type.includes('application/json') ? await r.json() : await r.text();
  if (!r.ok) {
    throw new Error(body?.detail ? String(body.detail) : `${method} ${path} failed (${r.status})`);
  }
  return body;
}

const YT_RE = /(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/|live\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/;
export const youtubeId = (url) => (url && url.match(YT_RE)?.[1]) || null;
export const youtubeThumb = (id) => `https://i.ytimg.com/vi/${id}/mqdefault.jpg`;

// YouTube oEmbed: CORS-enabled, no key. Cached per URL for the page lifetime.
const titleCache = new Map();
export async function youtubeTitle(url) {
  if (titleCache.has(url)) return titleCache.get(url);
  try {
    const r = await fetch(`https://www.youtube.com/oembed?url=${encodeURIComponent(url)}&format=json`);
    const title = r.ok ? (await r.json()).title || null : null;
    titleCache.set(url, title);
    return title;
  } catch {
    return null;
  }
}

// SomaFM publishes a logo for each station id (the stream file name).
export function somafmLogo(url) {
  const m = url.match(/somafm\.com\/([a-z0-9]+?)(?:\d{2,3})?\.pls$/i);
  return m ? `https://api.somafm.com/logos/512/${m[1]}512.png` : null;
}

export const hostOf = (url) => {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url; }
};

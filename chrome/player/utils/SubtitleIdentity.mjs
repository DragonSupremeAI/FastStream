// Keep normalization in sync with SubtitleCatAPI/extension/subtitle-identity.mjs.
export function detectSubtitleCode(value) {
  const text = String(value || '').normalize('NFKC');
  // Accept release suffixes such as "uc", but never truncate a longer number.
  // Two-letter prefixes cover releases such as AP-334; keep all three digits.
  const match = text.match(/(?:^|[^a-z0-9])([a-z]{2,5})[-\s._]*([0-9]{3})[a-z]*(?=$|[^a-z0-9])/i);
  return match ? `${match[1]}-${match[2]}`.toUpperCase() : null;
}

export function subtitleLanguage(filename) {
  const match = filename.match(/[._-]([a-z]{2,3}(?:-[a-z]{2})?)(?:\s*\(\d+\))?\.srt$/i);
  return match ? match[1].toLowerCase() : null;
}

// Tiny SQL tokenizer for the evidence panel. Returns [{ type, text }] so the
// component renders plain spans — no HTML injection surface. Types: keyword,
// function, string, number, comment, punct, plain.

const KEYWORDS = new Set(
  (
    'select from where group by order having join left right inner outer on as and or not in is null ' +
    'case when then else end with union all distinct limit offset between like exists over partition ' +
    'asc desc cast interval date current_date using cross lateral qualify'
  ).split(' '),
);

const FUNCTIONS = new Set(
  (
    'count sum avg min max round coalesce concat datediff date_add date_sub year month day rank ' +
    'dense_rank row_number lag lead abs floor ceil nullif greatest least percentile approx_percentile'
  ).split(' '),
);

const TOKEN_RE = /(--[^\n]*)|('(?:[^'\\]|\\.)*')|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_]*)|(\s+)|(.)/g;

export function tokenizeSql(sql) {
  if (!sql) return [];
  const tokens = [];
  let match;
  TOKEN_RE.lastIndex = 0;
  while ((match = TOKEN_RE.exec(sql)) !== null) {
    const [text, comment, string, number, word] = match;
    if (comment) tokens.push({ type: 'comment', text });
    else if (string) tokens.push({ type: 'string', text });
    else if (number) tokens.push({ type: 'number', text });
    else if (word) {
      const lower = word.toLowerCase();
      if (KEYWORDS.has(lower)) tokens.push({ type: 'keyword', text });
      else if (FUNCTIONS.has(lower)) tokens.push({ type: 'function', text });
      else tokens.push({ type: 'plain', text });
    } else tokens.push({ type: 'plain', text });
  }
  return tokens;
}

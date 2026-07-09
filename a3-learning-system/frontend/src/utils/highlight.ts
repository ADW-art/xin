/*
  共享代码高亮工具 (shared syntax highlighting utility)

  作用：
    提供多语言代码语法高亮和 base64 编解码工具函数
    ChatMessage.vue 和 CodeCard.vue 共用此模块

  高亮方案：正则匹配 → 注入 CSS class → CSS 着色
  覆盖语言：Python / JS/TS / Bash / SQL / JSON / HTML/XML / CSS/SCSS / YAML / C/C++ / Java / Go / Rust
*/

/* ── SVG icons ── */
export const SVG_COPY =
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
export const SVG_CHECK =
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'

/* ── LRU cache ── */
const _hlCache = new Map<string, string>()
const HL_CACHE_MAX = 100

/* ── base64 编解码 (UTF-8 安全) ── */
export function safeBtoa(str: string): string {
  const bytes = new TextEncoder().encode(str)
  let binary = ''
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}

export function safeAtob(encoded: string): string {
  const binary = atob(encoded)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i)
  }
  return new TextDecoder().decode(bytes)
}

/* ── HTML 清理：剥离 LLM 可能输出的语法高亮标签残渣 ── */
function stripHtmlTags(code: string): string {
  return code
    .replace(/<span\b[^>]*>/gi, '')
    .replace(/<\/span>/gi, '')
    .replace(/&lt;span\b[^&]*&gt;/gi, '')
    .replace(/&lt;\/span&gt;/gi, '')
    .replace(/<div\b[^>]*>/gi, '')
    .replace(/<\/div>/gi, '')
    .replace(/<code\b[^>]*>/gi, '')
    .replace(/<\/code>/gi, '')
    .replace(/<pre\b[^>]*>/gi, '')
    .replace(/<\/pre>/gi, '')
    .replace(/"(?:sk|ss|sc|sn|sf|sd|hl|k|n|s|f|d|c|o|p|w|kc|kp)">/gi, '')
    .replace(/\s*class\s*=\s*"(?:sk|ss|sc|sn|sf|sd)[^"]*"/gi, '')
}

/* ── HTML 转义 ── */
function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/* ── 多语言语法高亮 ── */
export function highlightCode(code: string, lang?: string): string {
  const cacheKey = `${lang || 'text'}:${code.slice(0, 200)}`
  if (_hlCache.has(cacheKey)) return _hlCache.get(cacheKey)!

  let cleaned = stripHtmlTags(code)
  let escaped = escapeHtml(cleaned)

  if (!lang || lang === 'text' || lang === 'plaintext' || lang === 'plain') {
    return escaped
  }

  if (lang === 'python' || lang === 'py') {
    const kw =
      'False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield'
    escaped = escaped.replace(new RegExp(`\\b(${kw})\\b`, 'g'), '<span class="sk">$1</span>')
    escaped = escaped.replace(/(@\w+)/g, '<span class="sd">$1</span>')
    escaped = escaped.replace(/\b([a-zA-Z_]\w*)(\s*\()/g, '<span class="sf">$1</span>$2')
    escaped = escaped.replace(/(#.*)$/gm, '<span class="sc">$1</span>')
    escaped = escaped.replace(/("""[\s\S]*?""")/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/("(?:[^"\\]|\\.)*")/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/('''[\s\S]*?''')/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/('(?:[^'\\]|\\.)*')/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/\b(\d+\.?\d*)\b/g, '<span class="sn">$1</span>')
  } else if (lang === 'javascript' || lang === 'js' || lang === 'typescript' || lang === 'ts') {
    const kw =
      'break|case|catch|class|const|continue|debugger|default|delete|do|else|export|extends|finally|for|function|if|import|in|instanceof|let|new|return|super|switch|this|throw|try|typeof|var|void|while|with|yield|async|await|from|of|static|enum|interface|type|implements'
    escaped = escaped.replace(new RegExp(`\\b(${kw})\\b`, 'g'), '<span class="sk">$1</span>')
    escaped = escaped.replace(/(\/\/.*)$/gm, '<span class="sc">$1</span>')
    escaped = escaped.replace(/("(?:[^"\\]|\\.)*")/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/('(?:[^'\\]|\\.)*')/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/(`(?:[^`\\]|\\.)*`)/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/\b(\d+\.?\d*)\b/g, '<span class="sn">$1</span>')
  } else if (lang === 'bash' || lang === 'sh' || lang === 'shell') {
    escaped = escaped.replace(/(#.*)$/gm, '<span class="sc">$1</span>')
    escaped = escaped.replace(/("(?:[^"\\]|\\.)*")/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/('(?:[^'\\]|\\.)*')/g, '<span class="ss">$1</span>')
    const cmds =
      'echo|cd|ls|cp|mv|rm|mkdir|git|npm|pip|python|node|docker|curl|wget|export|source|chmod|cat|grep|find|sed|awk|tar|ssh|scp|sudo|apt|brew|yarn|pnpm|npx|uvicorn|docker-compose|ps|kill'
    escaped = escaped.replace(new RegExp(`\\b(${cmds})\\b`, 'g'), '<span class="sk">$1</span>')
  } else if (lang === 'sql') {
    const kw =
      'SELECT|FROM|WHERE|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|TABLE|ALTER|DROP|INDEX|JOIN|INNER|LEFT|RIGHT|OUTER|ON|AS|AND|OR|NOT|NULL|IS|LIKE|BETWEEN|IN|ORDER|BY|GROUP|HAVING|LIMIT|OFFSET|COUNT|SUM|AVG|MAX|MIN|DISTINCT|PRIMARY|KEY|FOREIGN|REFERENCES|INT|VARCHAR|TEXT|BOOLEAN|DATETIME|JSON'
    escaped = escaped.replace(new RegExp(`\\b(${kw})\\b`, 'gi'), '<span class="sk">$1</span>')
    escaped = escaped.replace(/('(?:[^'\\]|\\.)*')/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/\b(\d+\.?\d*)\b/g, '<span class="sn">$1</span>')
  } else if (lang === 'json') {
    escaped = escaped.replace(/("(?:[^"\\]|\\.)*")(\s*:)/g, '<span class="sk">$1</span>$2')
    escaped = escaped.replace(/:\s*("(?:[^"\\]|\\.)*")/g, ': <span class="ss">$1</span>')
    escaped = escaped.replace(/\b(true|false|null)\b/g, '<span class="sk">$1</span>')
    escaped = escaped.replace(/\b(\d+\.?\d*)\b/g, '<span class="sn">$1</span>')
  } else if (lang === 'html' || lang === 'xml' || lang === 'svg') {
    escaped = escaped.replace(/(&lt;\/?)([\w-]+)/g, '$1<span class="sk">$2</span>')
    escaped = escaped.replace(/\s([\w-]+)(=)/g, ' <span class="sf">$1</span>$2')
    escaped = escaped.replace(/("(?:[^"\\]|\\.)*")/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/(&lt;!--[\s\S]*?--&gt;)/g, '<span class="sc">$1</span>')
  } else if (lang === 'css' || lang === 'scss') {
    escaped = escaped.replace(/(\/\*[\s\S]*?\*\/)/g, '<span class="sc">$1</span>')
    escaped = escaped.replace(/([.#@][\w-]+)/g, '<span class="sk">$1</span>')
    escaped = escaped.replace(/:([\w-]+)/g, ':<span class="sf">$1</span>')
    escaped = escaped.replace(/("(?:[^"\\]|\\.)*")/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/\b(\d+\.?\d*(?:px|em|rem|%|vh|vw|s|ms)?)\b/g, '<span class="sn">$1</span>')
  } else if (lang === 'yaml' || lang === 'yml') {
    escaped = escaped.replace(/(#.*)$/gm, '<span class="sc">$1</span>')
    escaped = escaped.replace(/^(\s*)([\w-]+)(:)/gm, '$1<span class="sk">$2</span>$3')
    escaped = escaped.replace(/("(?:[^"\\]|\\.)*")/g, '<span class="ss">$1</span>')
  } else if (lang === 'cpp' || lang === 'c++' || lang === 'c') {
    const kw =
      'int|float|double|char|void|bool|class|struct|namespace|using|template|typename|virtual|override|public|private|protected|const|static|auto|return|if|else|for|while|do|switch|case|break|continue|new|delete|nullptr|true|false|include|define|typedef|sizeof|try|catch|throw|std|cout|cin|endl|vector|string|map|set|pair|unique_ptr|shared_ptr|constexpr|noexcept|enum|explicit|friend|inline|long|short|signed|unsigned|union|volatile|wchar_t'
    escaped = escaped.replace(new RegExp(`\\b(${kw})\\b`, 'g'), '<span class="sk">$1</span>')
    escaped = escaped.replace(/(#.*)$/gm, '<span class="sc">$1</span>')
    escaped = escaped.replace(/(\/\/.*)$/gm, '<span class="sc">$1</span>')
    escaped = escaped.replace(/("(?:[^"\\]|\\.)*")/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/\b([a-zA-Z_]\w*)(\s*\()/g, '<span class="sf">$1</span>$2')
    escaped = escaped.replace(/\b(\d+\.?\d*)\b/g, '<span class="sn">$1</span>')
  } else if (lang === 'java') {
    const kw =
      'public|private|protected|class|interface|extends|implements|static|final|void|int|long|double|float|boolean|char|String|return|if|else|for|while|do|switch|case|break|continue|new|this|super|try|catch|throw|throws|import|package|null|true|false|abstract|synchronized|volatile|transient|enum|instanceof|native|strictfp|assert|default'
    escaped = escaped.replace(new RegExp(`\\b(${kw})\\b`, 'g'), '<span class="sk">$1</span>')
    escaped = escaped.replace(/(\/\/.*)$/gm, '<span class="sc">$1</span>')
    escaped = escaped.replace(/("(?:[^"\\]|\\.)*")/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/('(?:[^'\\]|\\.)*')/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/\b([a-zA-Z_]\w*)(\s*\()/g, '<span class="sf">$1</span>$2')
    escaped = escaped.replace(/\b(\d+\.?\d*)\b/g, '<span class="sn">$1</span>')
  } else if (lang === 'go' || lang === 'golang') {
    const kw =
      'func|var|const|type|struct|interface|map|chan|defer|go|return|if|else|for|range|switch|case|break|continue|fallthrough|import|package|nil|true|false|make|new|append|len|cap|select|goto|int|int8|int16|int32|int64|uint|uint8|uint16|uint32|uint64|float32|float64|string|bool|byte|rune|error'
    escaped = escaped.replace(new RegExp(`\\b(${kw})\\b`, 'g'), '<span class="sk">$1</span>')
    escaped = escaped.replace(/(\/\/.*)$/gm, '<span class="sc">$1</span>')
    escaped = escaped.replace(/("(?:[^"\\]|\\.)*")/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/(`(?:[^`\\]|\\.)*`)/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/\b([a-zA-Z_]\w*)(\s*\()/g, '<span class="sf">$1</span>$2')
    escaped = escaped.replace(/\b(\d+\.?\d*)\b/g, '<span class="sn">$1</span>')
  } else if (lang === 'rust' || lang === 'rs') {
    const kw =
      'fn|let|mut|struct|impl|trait|enum|match|use|mod|pub|self|super|where|as|ref|loop|while|for|if|else|return|break|continue|in|move|async|await|Some|None|Ok|Err|Result|Option|Vec|String|const|static|type|dyn|unsafe|extern|crate|macro_rules|true|false|box|drop'
    escaped = escaped.replace(new RegExp(`\\b(${kw})\\b`, 'g'), '<span class="sk">$1</span>')
    escaped = escaped.replace(/(\/\/.*)$/gm, '<span class="sc">$1</span>')
    escaped = escaped.replace(/(\/\*[\s\S]*?\*\/)/g, '<span class="sc">$1</span>')
    escaped = escaped.replace(/("(?:[^"\\]|\\.)*")/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/\b([a-zA-Z_]\w*)(\s*\()/g, '<span class="sf">$1</span>$2')
    escaped = escaped.replace(/('(?:[^'\\]|\\.)*')/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(
      /\b(\d+\.?\d*(?:u8|u16|u32|u64|i8|i16|i32|i64|f32|f64|usize|isize)?)\b/g,
      '<span class="sn">$1</span>',
    )
  }

  // LRU 淘汰
  if (_hlCache.size >= HL_CACHE_MAX) {
    const firstKey = _hlCache.keys().next().value
    if (firstKey) _hlCache.delete(firstKey)
  }
  _hlCache.set(cacheKey, escaped)

  return escaped
}

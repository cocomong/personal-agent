/*
 * miniMustache — a dependency-free Mustache subset, embedded verbatim into the
 * n8n invoice-render Code nodes (n8n has no template engine and its sandbox
 * has no module system, so mustache.js's UMD wrapper is a liability here).
 *
 * Supported syntax (exactly what backend/templates/invoice.html uses):
 *   {{name}}        HTML-escaped value from the context stack
 *   {{{name}}}      raw value (no escaping)
 *   {{#key}}...{{/key}}  section: array -> loop (empty array renders nothing),
 *                        truthy -> render once with the value pushed,
 *                        falsy/missing (0, '', null, undefined) -> skip
 *   {{^key}}...{{/key}}  inverted section: renders only when the value is
 *                        falsy or an empty array
 * Names may use dotted paths (a.b.c). Unknown names render as ''.
 *
 * Node test harness: `node backend/templates/mustache_mini.test.js`
 * (exports via CommonJS when available; a plain function otherwise).
 */
function miniMustache(template, data) {
  // HTML comments never reach the output — and this template's own header
  // comment documents the syntax with literal {{...}} examples, so they must
  // not be tokenized.
  template = String(template).replace(/<!--[\s\S]*?-->/g, '');

  // Escape map built without literal entity text in the source.
  const AMP = String.fromCharCode(38);
  const ENT = {
    [String.fromCharCode(38)]: AMP + 'amp;',
    [String.fromCharCode(60)]: AMP + 'lt;',
    [String.fromCharCode(62)]: AMP + 'gt;',
    [String.fromCharCode(34)]: AMP + 'quot;',
    [String.fromCharCode(39)]: AMP + '#39;',
  };
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ENT[c]);
  }

  function lookup(stack, name) {
    const parts = name.split('.');
    for (let i = stack.length - 1; i >= 0; i--) {
      let v = stack[i];
      let ok = true;
      for (const p of parts) {
        if (v == null || typeof v !== 'object' || !(p in v)) { ok = false; break; }
        v = v[p];
      }
      if (ok) return v;
    }
    return undefined;
  }

  function isTruthy(v) {
    if (Array.isArray(v)) return v.length > 0;
    return Boolean(v);
  }

  // tokenize: walk the template, producing text / tag tokens
  const tokens = [];
  let i = 0;
  while (i < template.length) {
    const open = template.indexOf('{{', i);
    if (open === -1) { tokens.push({ t: 'text', v: template.slice(i) }); break; }
    if (open > i) tokens.push({ t: 'text', v: template.slice(i, open) });
    let raw = false, inner;
    if (template.slice(open, open + 3) === '{{{') {
      const close = template.indexOf('}}}', open + 3);
      if (close === -1) throw new Error('unterminated {{{ in template');
      inner = template.slice(open + 3, close);
      raw = true;
      i = close + 3;
    } else {
      const close = template.indexOf('}}', open + 2);
      if (close === -1) throw new Error('unterminated {{ in template');
      inner = template.slice(open + 2, close);
      i = close + 2;
    }
    const m = inner.match(/^\s*(#|\^|\/)?\s*([\w.]+)\s*$/);
    if (!m) throw new Error('bad tag: ' + inner);
    tokens.push({ t: m[1] || 'var', name: m[2], raw: raw });
  }

  // parse into a tree (sections nest)
  function parse(start, end) {
    const nodes = [];
    let i = start;
    while (i < end) {
      const tok = tokens[i];
      if (tok.t === 'text' || tok.t === 'var') { nodes.push(tok); i++; continue; }
      if (tok.t === '/') throw new Error('unexpected {{/' + tok.name + '}}');
      const close = tokens.findIndex((t, j) => j > i && t.t === '/' && t.name === tok.name);
      if (close === -1 || close >= end) throw new Error('unclosed section {{' + tok.t + tok.name + '}}');
      nodes.push({ t: tok.t, name: tok.name, body: parse(i + 1, close) });
      i = close + 1;
    }
    return nodes;
  }
  const tree = parse(0, tokens.length);

  function renderNodes(nodes, stack) {
    let out = '';
    for (const n of nodes) {
      if (n.t === 'text') { out += n.v; continue; }
      const v = lookup(stack, n.name);
      if (n.t === 'var') {
        const s = v == null ? '' : v;
        out += n.raw ? String(s) : escapeHtml(s);
      } else if (n.t === '#') {
        if (Array.isArray(v)) {
          for (const item of v) out += renderNodes(n.body, stack.concat([item]));
        } else if (isTruthy(v)) {
          out += renderNodes(n.body, stack.concat([v]));
        }
      } else if (n.t === '^') {
        if (!isTruthy(v)) out += renderNodes(n.body, stack);
      }
    }
    return out;
  }

  return renderNodes(tree, [data]);
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { render: miniMustache };
}

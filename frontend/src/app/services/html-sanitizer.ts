// Sanitizador de HTML para las respuestas del chat. El backend genera tablas
// HTML con un LLM, así que no se puede confiar ciegamente en el contenido:
// se permite solo un conjunto de tags de presentación y se eliminan todos los
// atributos salvo los estructurales de tabla.
const ALLOWED_TAGS = new Set([
  'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption',
  'p', 'br', 'hr', 'b', 'strong', 'i', 'em', 'u', 'span', 'div',
  'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'code', 'pre', 'small', 'sub', 'sup',
]);

const ALLOWED_ATTRS = new Set(['colspan', 'rowspan']);

export function sanitizeChatHtml(raw: string): string {
  const doc = new DOMParser().parseFromString(raw, 'text/html');

  const walk = (node: Element) => {
    for (const child of Array.from(node.children)) {
      const tag = child.tagName.toLowerCase();
      if (!ALLOWED_TAGS.has(tag)) {
        // Conserva el texto interno pero elimina el elemento peligroso,
        // salvo scripts/estilos que se descartan por completo.
        if (tag === 'script' || tag === 'style' || tag === 'iframe' || tag === 'object' || tag === 'embed') {
          child.remove();
        } else {
          child.replaceWith(...Array.from(child.childNodes));
        }
        continue;
      }
      for (const attr of Array.from(child.attributes)) {
        if (!ALLOWED_ATTRS.has(attr.name.toLowerCase())) {
          child.removeAttribute(attr.name);
        }
      }
      walk(child);
    }
  };

  walk(doc.body);
  return doc.body.innerHTML;
}

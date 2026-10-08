import DOMPurify from 'dompurify';
import { marked } from 'marked';

/** Sanitize after Markdown conversion, including raw HTML and URL attributes. */
export function renderMarkdown(content: string): string {
	return DOMPurify.sanitize(marked.parse(content, { async: false }), {
		USE_PROFILES: { html: true }
	});
}

/** Keep the HTML insertion at the same boundary as sanitization. */
export function markdownPreview(node: HTMLElement, content: string) {
	const update = (value: string) => {
		node.innerHTML = renderMarkdown(value);
	};
	update(content);
	return { update };
}

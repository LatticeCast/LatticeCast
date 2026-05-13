// $lib/components/table/dragReorder.svelte.ts
//
// Shared HTML5 drag-to-reorder helper used by both the table-column header
// (TableGrid) and the view tabs (ViewSwitcher). Previously each call site
// inlined its own ondragstart/over/drop handlers and forgot to set
// `dataTransfer.effectAllowed` + `dropEffect` — Chromium silently cancels
// the drop in that case, so neither drag actually worked.
//
// Usage:
//   const drag = createDragReorder<MyItem>({
//     getId: (item) => item.id,
//     canDrag: (item) => !item.fixed,
//     onReorder: (fromId, toId) => reorder(fromId, toId),
//   });
//   // in the template:
//   {#each items as item (item.id)}
//     <div {...drag.handlers(item)}>...</div>
//   {/each}

export interface DragReorderOptions<T> {
	getId: (item: T) => string;
	onReorder: (fromId: string, toId: string) => void;
	canDrag?: (item: T) => boolean;
}

export interface DragReorderHandlers {
	draggable: boolean;
	'data-drag-over': 'true' | undefined;
	ondragstart: (e: DragEvent) => void;
	ondragover: (e: DragEvent) => void;
	ondrop: (e: DragEvent) => void;
	ondragend: () => void;
}

export function createDragReorder<T>(opts: DragReorderOptions<T>) {
	const canDrag = opts.canDrag ?? (() => true);
	let dragId = $state<string | null>(null);
	let dragOverId = $state<string | null>(null);

	function clear() {
		dragId = null;
		dragOverId = null;
	}

	return {
		get dragId() {
			return dragId;
		},
		get dragOverId() {
			return dragOverId;
		},
		handlers(item: T): DragReorderHandlers {
			const id = opts.getId(item);
			const allowed = canDrag(item);
			return {
				draggable: allowed,
				'data-drag-over': dragOverId === id && dragId !== id ? 'true' : undefined,
				ondragstart: (e: DragEvent) => {
					if (!allowed) return;
					if (e.dataTransfer) {
						e.dataTransfer.effectAllowed = 'move';
						// setData is required in Firefox; harmless in Chromium.
						e.dataTransfer.setData('text/plain', id);
					}
					dragId = id;
				},
				ondragover: (e: DragEvent) => {
					// We must preventDefault *and* set dropEffect to 'move' for
					// the drop event to fire under Chromium's default policy.
					if (dragId === null || !allowed) return;
					e.preventDefault();
					if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
					if (dragOverId !== id) dragOverId = id;
				},
				ondrop: (e: DragEvent) => {
					e.preventDefault();
					if (dragId && dragId !== id && allowed) opts.onReorder(dragId, id);
					clear();
				},
				ondragend: clear
			};
		}
	};
}

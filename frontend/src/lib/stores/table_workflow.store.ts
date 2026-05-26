import { writable } from 'svelte/store';
import type { Node, Edge, XYPosition } from '@xyflow/svelte';
import type { Row, Column } from '$lib/types/table';
import { createRow, updateRow, deleteRow, updateColumn } from '$lib/backend/tables';

export const screenToFlowStore = writable<(p: XYPosition) => XYPosition>(() => ({ x: 0, y: 0 }));

export const NODE_TYPES = ['START', 'STEP', 'TOOL', 'CONDITION', 'INFO', 'SUBGRAPH'] as const;

export const NODE_COLORS: Record<string, string> = {
	START: '#4ade80',
	STEP: '#60a5fa',
	TOOL: '#facc15',
	CONDITION: '#a78bfa',
	INFO: '#9ca3af',
	SUBGRAPH: '#f97316'
};

export function findColId(columns: Column[], name: string): string | null {
	return columns.find((c) => c.name === name)?.column_id ?? null;
}

export function deriveGraphNames(rows: Row[], columns: Column[]): string[] {
	const graphCol = findColId(columns, 'graph_name');
	if (!graphCol) return ['root'];
	const col = columns.find((c) => c.column_id === graphCol);
	if (col?.options?.choices) return col.options.choices.map((c) => c.value);
	const names = new Set<string>();
	for (const r of rows) {
		const v = r.row_data[graphCol] as string;
		if (v) names.add(v);
	}
	return names.size ? [...names] : ['root'];
}

export function filterGraphRows(rows: Row[], columns: Column[], graphName: string): Row[] {
	const graphCol = findColId(columns, 'graph_name');
	return rows.filter((r) => {
		const gn = graphCol ? (r.row_data[graphCol] as string) : null;
		return !gn || gn === graphName;
	});
}

export function deriveNodes(rows: Row[], columns: Column[]): Node[] {
	const nameCol = findColId(columns, 'name');
	const typeCol = findColId(columns, 'type');
	const descCol = findColId(columns, 'description');
	const posXCol = findColId(columns, 'pos_x');
	const posYCol = findColId(columns, 'pos_y');

	return rows.map((row, i) => ({
		id: String(row.row_id),
		type: 'workflowNode',
		position: {
			x: posXCol ? Number(row.row_data[posXCol] ?? i * 300) : i * 300,
			y: posYCol ? Number(row.row_data[posYCol] ?? 0) : 0
		},
		data: {
			label: nameCol ? String(row.row_data[nameCol] ?? `Node ${row.row_id}`) : `Node ${row.row_id}`,
			nodeType: typeCol ? String(row.row_data[typeCol] ?? 'STEP') : 'STEP',
			description: descCol ? String(row.row_data[descCol] ?? '') : '',
			row
		}
	}));
}

export function deriveEdges(rows: Row[], columns: Column[]): Edge[] {
	const nextsCol = findColId(columns, 'nexts');
	const trueNextCol = findColId(columns, 'true_next');
	const falseNextCol = findColId(columns, 'false_next');
	const rowIds = new Set(rows.map((r) => String(r.row_id)));
	const edges: Edge[] = [];

	for (const row of rows) {
		const srcId = String(row.row_id);

		if (nextsCol) {
			let arr: string[] = [];
			try {
				const raw = row.row_data[nextsCol];
				if (typeof raw === 'string') arr = JSON.parse(raw);
			} catch {}
			for (const targetId of arr) {
				if (rowIds.has(targetId)) {
					edges.push({
						id: `e-${srcId}-${targetId}`,
						source: srcId,
						target: targetId,
						style: 'stroke-width: 3px;'
					});
				}
			}
		}

		if (trueNextCol) {
			const target = row.row_data[trueNextCol] as string;
			if (target && rowIds.has(target)) {
				edges.push({
					id: `e-${srcId}-true-${target}`,
					source: srcId,
					sourceHandle: 'true',
					target,
					style: 'stroke-width: 3px; stroke: #22c55e;'
				});
			}
		}

		if (falseNextCol) {
			const target = row.row_data[falseNextCol] as string;
			if (target && rowIds.has(target)) {
				edges.push({
					id: `e-${srcId}-false-${target}`,
					source: srcId,
					sourceHandle: 'false',
					target,
					style: 'stroke-width: 3px; stroke: #ef4444;'
				});
			}
		}
	}

	return edges;
}

// ─── Mutations (all go through BE → rows store → $derived re-renders) ────────

export async function addNode(
	tableId: string,
	columns: Column[],
	graphName: string,
	x: number,
	y: number
): Promise<Row> {
	const data: Record<string, unknown> = {};
	const set = (name: string, val: unknown) => {
		const id = findColId(columns, name);
		if (id) data[id] = val;
	};
	set('name', 'New Node');
	set('type', 'STEP');
	set('description', '');
	set('graph_name', graphName);
	set('nexts', '[]');
	set('true_next', '');
	set('false_next', '');
	set('pos_x', Math.round(x));
	set('pos_y', Math.round(y));
	return createRow(tableId, { row_data: data });
}

export async function deleteNode(
	tableId: string,
	rows: Row[],
	columns: Column[],
	rowId: number
): Promise<void> {
	const targetId = String(rowId);
	const nextsCol = findColId(columns, 'nexts');
	const trueNextCol = findColId(columns, 'true_next');
	const falseNextCol = findColId(columns, 'false_next');

	const cleanups: Promise<unknown>[] = [];
	for (const row of rows) {
		if (row.row_id === rowId) continue;
		const patch: Record<string, unknown> = {};
		let dirty = false;

		if (nextsCol) {
			let arr: string[] = [];
			try {
				const raw = row.row_data[nextsCol];
				if (typeof raw === 'string') arr = JSON.parse(raw);
			} catch {}
			if (arr.includes(targetId)) {
				patch[nextsCol] = JSON.stringify(arr.filter((id) => id !== targetId));
				dirty = true;
			}
		}
		if (trueNextCol && row.row_data[trueNextCol] === targetId) {
			patch[trueNextCol] = '';
			dirty = true;
		}
		if (falseNextCol && row.row_data[falseNextCol] === targetId) {
			patch[falseNextCol] = '';
			dirty = true;
		}
		if (dirty) {
			cleanups.push(
				updateRow(tableId, row.row_id, {
					row_data: { ...row.row_data, ...patch }
				})
			);
		}
	}
	await Promise.all(cleanups);
	await deleteRow(tableId, rowId);
}

export async function removeEdgeByParts(
	tableId: string,
	rows: Row[],
	columns: Column[],
	sourceRowId: number,
	handle: string | null,
	targetRowId: string
): Promise<void> {
	const row = rows.find((r) => r.row_id === sourceRowId);
	if (!row) return;

	const nextsCol = findColId(columns, 'nexts');
	const trueNextCol = findColId(columns, 'true_next');
	const falseNextCol = findColId(columns, 'false_next');
	const newData = { ...row.row_data };

	if (handle === 'true' && trueNextCol) {
		newData[trueNextCol] = '';
	} else if (handle === 'false' && falseNextCol) {
		newData[falseNextCol] = '';
	} else if (nextsCol) {
		let arr: string[] = [];
		try {
			const raw = newData[nextsCol];
			if (typeof raw === 'string') arr = JSON.parse(raw);
		} catch {}
		newData[nextsCol] = JSON.stringify(arr.filter((id) => id !== targetRowId));
	}

	await updateRow(tableId, row.row_id, { row_data: newData });
}

export function parseEdgeId(
	edgeId: string,
	edges: Edge[]
): {
	source: number;
	handle: string | null;
	target: string;
} | null {
	const edge = edges.find((e) => e.id === edgeId);
	if (!edge) return null;
	return {
		source: Number(edge.source),
		handle: edge.sourceHandle ?? null,
		target: edge.target
	};
}

// ─── Subgraph CRUD (mutates graph_name column choices) ───────────────────────

export async function addSubgraph(tableId: string, columns: Column[], name: string): Promise<void> {
	const col = columns.find((c) => c.name === 'graph_name');
	if (!col) return;
	const existing = col.options?.choices ?? [];
	if (existing.some((c) => c.value === name)) return;
	await updateColumn(tableId, col.column_id, {
		options: { ...col.options, choices: [...existing, { value: name, color: '#6b7280' }] }
	});
}

export async function renameSubgraph(
	tableId: string,
	columns: Column[],
	rows: Row[],
	oldName: string,
	newName: string
): Promise<void> {
	const col = columns.find((c) => c.name === 'graph_name');
	if (!col) return;
	const choices = (col.options?.choices ?? []).map((c) =>
		c.value === oldName ? { ...c, value: newName } : c
	);
	const graphCol = col.column_id;

	const updates = rows
		.filter((r) => r.row_data[graphCol] === oldName)
		.map((r) =>
			updateRow(tableId, r.row_id, {
				row_data: { ...r.row_data, [graphCol]: newName }
			})
		);

	await Promise.all([
		updateColumn(tableId, col.column_id, { options: { ...col.options, choices } }),
		...updates
	]);
}

export async function removeSubgraph(
	tableId: string,
	columns: Column[],
	rows: Row[],
	graphName: string
): Promise<void> {
	const col = columns.find((c) => c.name === 'graph_name');
	if (!col) return;
	const graphCol = col.column_id;
	const choices = (col.options?.choices ?? []).filter((c) => c.value !== graphName);

	const rowsToDelete = rows.filter((r) => r.row_data[graphCol] === graphName);
	const deletes = rowsToDelete.map((r) => deleteRow(tableId, r.row_id));

	await Promise.all([
		updateColumn(tableId, col.column_id, { options: { ...col.options, choices } }),
		...deletes
	]);
}

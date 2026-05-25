import type { Node, Edge } from '@xyflow/svelte';
import type { Row, Column } from '$lib/types/table';

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

export function filterGraphRows(
	rows: Row[],
	columns: Column[],
	graphName: string
): Row[] {
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
			label: nameCol
				? String(row.row_data[nameCol] ?? `Node ${row.row_id}`)
				: `Node ${row.row_id}`,
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

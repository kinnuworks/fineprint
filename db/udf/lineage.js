// Lineage walks that visit each model once, however many merge paths lead to it.

const LINEAGE = ['FINETUNE_OF', 'ADAPTER_OF', 'MERGE_OF', 'QUANTIZED_FROM'];

function walk(start, direction, maxDepth, limit) {
    const seen = new Set([start.id]);
    const found = [];
    let frontier = [start];
    let depth = 0;
    while (frontier.length > 0 && depth < maxDepth && found.length < limit) {
        depth += 1;
        const next = [];
        // One traversal per relationship type: in FalkorDB v4.22.1 a `types` list
        // with more than one entry only follows the last type.
        for (const t of LINEAGE) {
            const layers = graph.traverse(frontier, {direction: direction, types: [t], returnType: 'nodes'});
            for (let i = 0; i < layers.length && found.length < limit; i++) {
                for (const n of layers[i]) {
                    if (seen.has(n.id)) continue;
                    seen.add(n.id);
                    found.push({node: n, depth: depth, parent: frontier[i], rel: t});
                    next.push(n);
                    if (found.length >= limit) break;
                }
            }
        }
        frontier = next;
    }
    return found;
}

// Ancestors with their distance: [{id, license, depth}]
function ancestors(start, maxDepth) {
    return walk(start, 'outgoing', maxDepth || 64, 100000).map(f => ({
        id: f.node.attributes.id,
        license: f.node.attributes.license,
        depth: f.depth,
        missing: f.node.attributes.missing === true,
        child: f.parent.attributes.id,
        relation: f.rel,
    }));
}

// Number of descendants, and the deepest level reached.
function descendantStats(start, maxDepth) {
    const found = walk(start, 'incoming', maxDepth || 64, 5000000);
    let deepest = 0;
    let downloads = 0;
    for (const f of found) {
        if (f.depth > deepest) deepest = f.depth;
        downloads += f.node.attributes.downloads || 0;
    }
    return {count: found.length, deepest: deepest, downloads: downloads};
}

// Descendant ids ranked by downloads, for takedown replays and family views.
function topDescendants(start, k) {
    const found = walk(start, 'incoming', 64, 5000000);
    found.sort((a, b) => (b.node.attributes.downloads || 0) - (a.node.attributes.downloads || 0));
    return found.slice(0, k || 50).map(f => ({
        id: f.node.attributes.id,
        license: f.node.attributes.license,
        downloads: f.node.attributes.downloads,
        depth: f.depth,
    }));
}

falkor.register('ancestors', ancestors);
falkor.register('descendantStats', descendantStats);
falkor.register('topDescendants', topDescendants);

// Ids of every model below any of the given roots (multi-source walk).
function descendantIds(roots) {
    const seen = new Set(roots.map(r => r.id));
    const out = [];
    let frontier = roots;
    while (frontier.length > 0) {
        const next = [];
        for (const t of LINEAGE) {
            const layers = graph.traverse(frontier, {direction: 'incoming', types: [t], returnType: 'nodes'});
            for (const layer of layers) {
                for (const n of layer) {
                    if (seen.has(n.id)) continue;
                    seen.add(n.id);
                    out.push(n.attributes.id);
                    next.push(n);
                }
            }
        }
        frontier = next;
    }
    return out;
}

falkor.register('descendantIds', descendantIds);

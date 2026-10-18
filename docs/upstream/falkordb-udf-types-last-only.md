# UDF getNeighbors / graph.traverse: a `types` list with more than one entry only follows the last type

Draft issue for FalkorDB/FalkorDB. Not filed yet.

## Version

`falkordb/falkordb:v4.22.1` (Docker), Redis 8.10.2, macOS arm64 host via OrbStack.

## Repro

```
GRAPH.QUERY g "CREATE (c:M {id:'child'})-[:A]->(p:M {id:'parent'})"
```

```javascript
// GRAPH.UDF LOAD dbg
function t(n, types, dir) { return n.getNeighbors({direction: dir, types: types}).map(x => x.attributes.id); }
falkor.register('t', t);
```

```
GRAPH.QUERY g "MATCH (m:M {id:'child'}) RETURN dbg.t(m, ['A','B'], 'outgoing'), dbg.t(m, ['B','A'], 'outgoing')"
```

Expected: `[parent]` for both calls.
Actual: `[]` for `['A','B']`, `[parent]` for `['B','A']`.

The same happens with `direction: 'incoming'` and `'both'`, and with `graph.traverse(sources, {types: [...]})`. Only the last element of `types` is used.

## Observed on real data

Graph of 3.16M Hugging Face models with FINETUNE_OF, ADAPTER_OF, MERGE_OF and QUANTIZED_FROM edges (927k lineage edges). For `QCRI/Fanar-2-27B-Instruct`, which has one outgoing FINETUNE_OF edge:

| types | direction | result |
|---|---|---|
| ['FINETUNE_OF','ADAPTER_OF'] | outgoing | [] |
| ['ADAPTER_OF','FINETUNE_OF'] | outgoing | [google/gemma-3-27b-pt] |
| ['QUANTIZED_FROM','FINETUNE_OF'] | incoming | [] |
| ['FINETUNE_OF','QUANTIZED_FROM'] | incoming | 4 quantized children |

## Workaround

Call `graph.traverse` once per relationship type and merge the results.

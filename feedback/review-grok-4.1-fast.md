# BlueClaw Spec Review — x-ai/grok-4.1-fast

## Overall Assessment
BlueClaw is a thoughtful layering of AT Protocol for social federation with A2A for agent tasks, leveraging existing infrastructure effectively without unnecessary reinvention. It correctly grasps AT Protocol concepts like DIDs, PDSes, relays, and lexicons, while proposing a pragmatic A2A bridge via projected records. However, it over-specifies AppView logic (e.g., reputation algorithms) that should remain decentralized, and several specs have inconsistencies or unaddressed edge cases that could break federation or adoption.

## Critical Issues (things that need to change)
1. **Lexicon inconsistencies**: `social.agent.reputation.dispute` is detailed in reputation.md but absent from lexicons.md; similarly, `social.agent.task.*` are promised but undefined. All lexicons must be fully specified in lexicons.md before claiming "draft completeness."
2. **Record key misuse**: `social.agent.graph.follow` uses TID keys, but follows are mutable (e.g., reason changes); use stable keys like `did:plc:...` (hashed or truncated) per AT Protocol best practices for graph edges to enable efficient updates without repo bloat.
3. **A2A bridge overreach**: DID-Auth JWS claims mandate `aud` matching receiver's DID, but A2A endpoints are HTTPS URLs, not DIDs—resolving this requires new A2A spec changes or fallback to bearer tokens; current flow assumes A2A supports unsolicited DID resolution, which it doesn't.
4. **Reputation stored on attester's PDS**: Attestations about subject S on attester A's PDS means A's downtime hides A's attestations; violates "data sovereignty" claim—move to neutral relay-indexed or dual-write (A and S PDSes).
5. **PDS impl guide ignores AT reference**: Recommends custom MST/SQLite impl despite `@atproto/repo` existing and being battle-tested; forking/reimplementing risks interop bugs—use the official lib or clearly warn of breakage.

## Gaps & Missing Pieces
1. **Task protocol lexicons**: architecture.md and bridge.md reference `social.agent.task.request/result` but they're only in "Future Lexicons"; without them, A2A delegation flow is incomplete (step 4 records task on A's PDS only).
2. **Human-agent boundary**: interop.md discusses dual-profiles but lacks Lexicon for human-operated agent declarations (e.g., `social.agent.operator.declaration`); open questions like "human-agent boundary" remain unanswered.
3. **Relay discovery**: Relays rely on manual registration or DID crawling, but no spec for PDS announcing itself (e.g., via DID service endpoint); PDSes are undiscoverable without operator intervention.
4. **Migration details**: pds-implementation.md covers export/import but ignores blob migration (CAR includes blobs? No—separate `listBlobs/getBlob` needed); also, no handling for in-flight relay subscriptions during DID rotation.
5. **Lexicon versioning**: No migration plan for Lexicon changes (e.g., adding required fields to `social.agent.feed.post`); AT Protocol requires NSID bumps for breaks.
6. **A2A sync failure modes**: bridge.md assumes agent runtime syncs card→record, but no handling if PDS rejects write (e.g., rate limit)—leads to stale discovery data.

## Security Concerns
1. **Sybil via cheap PDSes**: Claims PDS costs resist Sybil, but managed PDSes (Bluesky model) charge per-user minimally; reputation's graph analysis is good but compute-intensive per-query—relays will balk at running PageRank on millions of attestations.
2. **DID resolution DoS**: Discovery flows resolve DIDs multiple times (step 5 in relay search); no caching specified, opens PDS/PLC directory to amplification attacks from agent swarms.
3. **Replay in DID-Auth**: Nonce cache bounded at 10k but no eviction policy details (LRU?); 600s window + short exp is good, but no rate limit on auth attempts per DID pair.
4. **Operator DID spoofing**: `operator.did` in profile is self-claimed; no verification (e.g., bidirectional link), so Sybil operators fake org affiliation.
5. **Firehose spam**: No PDS-level filtering before `subscribeRepos`; high-volume agents (e.g., presence pings) flood relays without backpressure.
6. **A2A endpoint trust**: `a2aCard` URL fetched over HTTPS but no pinning or sig verification; operator misconfig exposes to endpoint hijacking.

## Strongest Aspects
1. **AT Protocol fidelity**: Accurately uses repos, lexicons, XRPC, firehose without mods; dual-namespace interop enables seamless human-agent mixing.
2. **A2A bridge design**: Projection model (AT record subsets A2A card) with sync triggers and verification (profile.a2aEndpoint == card URL) is elegant and eventual-consistent.
3. **Reputation as data**: Raw attestations protocolized, scores AppView-computed—decentralized, verifiable, domain-specific; Sybil defenses (conductance, bursts) are sophisticated.
4. **Reference impl plan**: Phased, dependency-graphed, with Docker/test infra—realistic path to MVP, leverages @atproto/* libs.
5. **Interop focus**: Dual-publishing, label propagation, migration paths make it Bluesky-compatible Day 1.

## Suggestions
1. **Modularize reputation**: Move algorithms (PageRank, decay) to separate spec or examples repo; protocol only defines attestation schema/query APIs.
2. **Add task lexicons now**: Define minimal `social.agent.task.request/completion` mirroring A2A request/response for full delegation flow.
3. **Standardize discovery**: Add `social.agent.discovery.index` record for PDS/relay self-announcement, crawlable via firehose.
4. **PDS proxy mode**: For embedded PDSes, spec a "proxy to hosted PDS" for writes (keeps runtime light, uses managed infra).
5. **Benchmark relay costs**: Simulate 10k agents/1M attestations on Postgres to validate graph analysis feasibility; fallback to simple average if needed.
6. **Operator verification flow**: Lexicon for operator→agent declaration + verification badge computation in AppViews.
7. **CLI-first tooling**: Expand CLI with `blueclaw playground` (TUI chat simulating agent interactions) for easier testing.

## Feasibility Rating
8

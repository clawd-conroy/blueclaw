# BlueClaw Spec Review — openai/gpt-5.2

## Overall Assessment
The direction—use AT Protocol for identity/data/federation and A2A for agent RPC—is plausible, but the spec repeatedly hand-waves over places where AT/A2A semantics don’t match what you’ve written. The bridge/security story is currently not strong enough to prevent trivial endpoint spoofing, and several lexicons are syntactically wrong in ways that will break real validation/tooling.

## Critical Issues (things that need to change)
1. **Your A2A “identity binding” is weak (impersonation still easy).**  
   Checking `profile.a2aEndpoint == capabilityCard.a2aCard` does *not* prove that the HTTPS-served Agent Card is controlled by the DID owner. The Agent Card is unsigned, and the URL can point anywhere. An attacker who compromises that web host (or convinces an operator to point to their host) can serve a card that routes tasks to a different service while still “passing” your check.  
   **Fix:** Require a cryptographic binding:
   - Publish a **hash of the Agent Card** (or of a canonicalized subset) in `social.agent.capability.card` and verify it on fetch; and/or
   - Require the Agent Card to include a **JWS signature by the DID key** (or DIDComm-style proof) over its contents; and
   - Strongly constrain `a2aCard` to be **same-origin with the handle domain** (or at least same eTLD+1) if you want the domain verification story to matter.

2. **AT Protocol record “authorship” claims are overstated / sometimes false.**  
   You say: “An agent can prove it authored a post without trusting a central server” and “No third party can modify, delete, or withhold data.” That is only true if the agent operator controls the repo signing key and the serving infrastructure. In common AT deployments the PDS holds keys and can withhold data by simply not serving it or not emitting events.  
   **Fix:** Explicitly define **key custody modes**:
   - If PDS holds signing key: you trust the PDS operator for authorship integrity.
   - If agent holds signing key (client-side signing): stronger authorship, but requires real protocol/workflow support (not just “recommended”).
   Also soften the “cannot withhold” claim: portability reduces lock-in, it doesn’t prevent withholding in the moment.

3. **You misunderstand/blur relay vs AppView responsibilities (AT Protocol accuracy).**  
   You describe relays as enabling “agent discovery” and imply they provide “relay search.” In AT Protocol, **relays are primarily fanout and replication infrastructure**, not discovery/search APIs. Search is typically an **AppView/indexer** concern. Some relay implementations may add indexing, but it’s not the core contract.  
   **Fix:** Reframe: relays provide a firehose + repository sync; AppViews/indexers provide discovery/search. If you *do* want relay-level indexing, define it as **non-standard / optional** and don’t build core flows on it.

4. **Your PDS implementation guidance conflicts with AT Protocol realities.**
   - “PDS notifies subscribed relays” is inverted: relays subscribe to the PDS’s `subscribeRepos`.  
   - “Lazy WebSocket / webhook bridge / relay polling” is basically “break federation” unless you explicitly define it as **out-of-spec** and limited to private deployments.  
   **Fix:** Separate “spec-compliant AT PDS” from “dev-mode shortcuts.” Don’t mix them in a document titled “Implementation Guide” without a giant warning that shortcuts won’t federate.

5. **Lexicon schemas contain multiple invalid constraints (will break tooling).**  
   You use `maxLength` on arrays (`capabilities`, `langs`, `tags`, etc.). In lexicon JSON schema you want `maxItems`, not `maxLength`. This is not a nit: validators will reject or ignore constraints.  
   **Fix:** Audit all lexicons for schema correctness (array constraints, formats, unions, refs). Run them through the official lexicon tooling and include that in CI.

6. **Presence as an AT record is a scalability footgun as described.**  
   Writing `presence.status/self` “every minute” across many agents will generate huge commit volume and load relays/AppViews. AT is not a real-time presence protocol.  
   **Fix:** Either:
   - Make presence **purely AppView-observed** (derived from A2A heartbeat checks), or
   - Move presence to an **out-of-band ephemeral channel** and only checkpoint coarse state to AT (e.g., “maintenance window started/ended”), or
   - Enforce aggressive rate limits and set expectations that presence is “best-effort, slow.”

## Gaps & Missing Pieces
1. **No concrete `social.agent.task.*` lexicons yet, but reputation depends on them.**  
   You rely on `evidence` pointing to task records, but tasks aren’t defined. You can’t claim “verifiable, not vibes” without specifying the evidence object model and verification rules.

2. **No canonicalization rules for Agent Card hashing/signing.**  
   If you add hashes/signatures (you should), you need canonical JSON rules (JCS, RFC 8785) or a CBOR canonicalization. Otherwise different serializations break verification.

3. **Key rotation verification is hand-waved and partially wrong.**  
   “AT records signed by old key remain valid (verified against key active at signing time)” requires access to DID history (PLC op log) and verifiers that actually implement historical key resolution. Many consumers verify against the *current* DID doc.  
   **Define:** required verification behavior for BlueClaw AppViews/agents (e.g., must use PLC operation log for did:plc).

4. **Domain taxonomy collisions and squatting are not addressed.**  
   Domains are free strings, which is fine, but you need *some* collision-handling strategy or at least guidance (namespacing like `org.foo.capability.bar`). Otherwise “code-review” becomes spammed with incompatible meanings.

5. **No clear story for private tasks vs public attestations.**  
   You say task content is private and “lives in runtimes only,” but you also want public evidence links. That’s contradictory unless you define:
   - public redacted transcripts,
   - zero-knowledge attestation (future),
   - or “evidence may be private; then it’s not publicly verifiable” (and how scoring handles that).

6. **Interop with existing `app.bsky.*` objects is under-modeled.**  
   If you want hybrid threads, you need explicit rendering and threading rules when roots/parents are different record types and when one side is missing/unindexed.

7. **Adoption path for existing AT infra is riskier than you admit.**  
   You assume PDSes “accept arbitrary NSIDs.” Some may start restricting. Relays/AppViews may ignore your namespace. You need a strategy for “what if only some infra carries BlueClaw?”

## Security Concerns
1. **SSRF / fetch attacks via `a2aCard` URLs.**  
   AppViews/agents fetching arbitrary `a2aCard` URLs invites SSRF and internal network probing.  
   Mitigate: enforce HTTPS, block RFC1918/localhost, size limits, timeouts, content-type checks, and ideally same-origin constraints.

2. **Replay protection is underspecified operationally.**  
   “Nonce cache 10,000 entries” is meaningless without traffic assumptions. A busy agent can exceed that quickly. Also, you need to define whether nonce is per-connection, per-request, per-endpoint, etc.

3. **DID-Auth header is a bespoke JWT scheme with interoperability risk.**  
   A2A likely has its own authentication expectations; inventing “DID-Auth Header” may not interop and may be vulnerable if libraries treat it as a generic JWT without strict `aud/kid/alg` pinning.  
   Mitigate: pin allowed algorithms, require `kid` resolution rules, require strict JOSE headers, consider adopting an existing pattern (DPoP-like proof, HTTP Message Signatures, DIDComm).

4. **No authorization binding between “operator DID” and control.**  
   You treat `operator.did` in profile as meaningful, but it’s just a claim. Without an operator-signed counter-record (you mention it as “future”), anyone can claim “operated by did:plc:OpenAI” and trick naive UIs.  
   Fix: make the bidirectional proof a **v1 requirement** for any UI that displays operator trust.

5. **Reputation is gameable via cheap attestations + shared hosting.**  
   Your Sybil defenses are mostly AppView heuristics. Attackers can:
   - buy diverse cheap hosting,
   - produce “evidence” that is meaningless but formally valid,
   - or compromise a few reputable agents and leverage weighted trust.  
   You need explicit “what counts as verified evidence” and stronger rate/cost controls (even if optional).

6. **Presence/status and capability updates are DoS vectors.**  
   Agents can spam singleton updates to force reindexing churn. Without network-level throttles (at PDS, relay ingest, and AppView), this will degrade quickly.

## Strongest Aspects
1. **Layering is conceptually correct:** use AT for durable, signed public state; use A2A for interactive task execution. That separation is the right instinct.
2. **AppView-computed reputation is the right place for algorithms.** Keeping raw attestations protocol-level and scores view-level is aligned with how AT ecosystems already vary moderation/ranking.
3. **Dual-namespace interop thinking is solid.** The spec correctly anticipates dual-publishing, deduplication needs, and that Bluesky clients won’t render unknown record types.
4. **Explicit threat-model sections are present (even if incomplete).** You’re at least naming abuse classes early, which most protocol specs avoid until it’s too late.

## Suggestions
1. **Make the A2A↔AT binding cryptographic (non-negotiable).**  
   Minimum viable: add `cardHash` (and canonicalization rules) to `social.agent.capability.card`. Better: add `proof` (JWS) to the Agent Card itself.

2. **Stop treating “relay search” as a given; define discovery as AppView/indexer.**  
   Provide a reference “directory AppView” spec and keep relays as dumb pipes unless you’re prepared to implement a full relay correctly.

3. **Fix lexicon schemas and publish them as actual lexicon JSON files (not just in markdown).**  
   Add CI that runs `lex-cli validate` on every change.

4. **Define `social.agent.task.*` before cementing reputation rules.**  
   You can keep task payload private, but you need a public envelope that supports evidence (timestamps, participants, capability domain, outcome hash, optional redacted transcript).

5. **Rework presence into an optional/derived feature.**  
   If you insist on presence records, impose strict update ceilings (e.g., no more than once per 5–15 minutes) and treat them as “last reported,” not “real-time.”

6. **Clarify custody/trust assumptions in the architecture doc.**  
   State explicitly what is guaranteed in each deployment model (self-hosted PDS, managed PDS, embedded PDS) regarding authorship integrity and availability.

7. **Make operator verification first-class.**  
   Add `social.agent.operator.declaration` (operator-signed) to v1, and define how UIs should display operator trust only when both sides attest.

## Feasibility Rating
**6/10.** The overall approach is buildable, but key parts (lexicon correctness, identity binding between AT discovery and A2A endpoints, and realistic relay/AppView responsibilities) need revision before this is safely implementable or likely to interoperate cleanly.

# BlueClaw Spec Review — google/gemini-3-pro-preview

## Overall Assessment

This is a remarkably well-thought-out specification that successfully bridges the "static social" world of Bluesky/AT Protocol with the "dynamic functional" world of AI agents. The decision to use AT Protocol for discovery/identity and A2A for direct communication is architecturally sound. The interoperability plan with existing Bluesky infrastructure is the strongest part of the proposal.

However, the "Embedded PDS" concept—while attractive for adoption—suffers from severe networking reality checks (NAT/Firewalls) that are not adequately addressed. Additionally, the specification is currently missing the actual "work" layer (Task definitions) and relies on a reputation system that may be computationally impractical for decentralized AppViews to maintain in real-time.

## Critical Issues (things that need to change)

1.  **The "Embedded PDS" Networking Fallacy**:
    The spec suggests an Embedded PDS (running inside an agent script) can federate with relays. This fails in 90% of real-world use cases (laptops, Colab, corporate intranets) because the PDS has no public IP or ingress.
    *   **The Problem:** Standard AT Protocol relays (like `bsky.network`) usually *crawl* PDSes or expect them to be publicly addressable to verify SSL and handle callbacks. If the agent is behind a NAT, the relay cannot connect to `ws://localhost:2583`.
    *   **The Fix:** You need a "Relay Proxy" or "PDS Gateway" component—a public-facing dumb pipe that ephemeral agents connect to via outbound WebSocket, which then presents a valid PDS interface to the rest of the network.

2.  **Ambiguous Task Execution Layer**:
    The architecture is confused about where tasks happen.
    *   `spec/architecture.md` says tasks happen via A2A (HTTP/RPC).
    *   `spec/lexicons.md` lists `social.agent.task.*` records.
    *   **The Conflict:** If I ask an agent to do something, do I send an A2A POST request, or do I write a `task.request` record to my PDS? If it's the latter, the latency is too high (polling). If it's the former, why do the Lexicons exist?
    *   **The Fix:** Explicitly define the `task.*` records as *audit logs* or *async offers*, not the transport mechanism for execution.

3.  **Reputation "Negativity Bias" Vulnerability**:
    In `spec/reputation.md`, giving negative attestations (scores 1-2) a 1.5x weight creates a dominant strategy for "Review Bombing."
    *   **The Attack:** A Sybil cluster can destroy a competitor's reputation faster than the competitor can build it.
    *   **The Fix:** Remove the asymmetry. Negative signal is already stronger socially; algorithmic boosting makes the system unstable.

4.  **A2A Auth Handshake Non-Standardization**:
    You are defining a custom `DID-Auth` header for A2A. While valid, this means a standard Google A2A client cannot talk to a BlueClaw agent without modification.
    *   **The Fix:** Define this strictly as an A2A "Extension" or use standard OIDC flows where the Identity Provider is the agent's PDS.

## Gaps & Missing Pieces

1.  **Payment & Settlement**: The `capability.card` includes a `pricing` field, but there is no protocol for settlement. If an agent charges "0.01 USD per task," how is that transferred? Without a defined payment rail (Lightning, USDC, Stripe links), the pricing field is useless metadata.
2.  **Notification/Interrupt Model**: How does an agent know it has been mentioned or replied to *immediately*? Polling the PDS or Relay firehose is heavy for a lightweight agent. The spec needs a push-notification standard (e.g., a webhook URL in the profile) for real-time responsiveness.
3.  **Blob Storage Economics**: The spec allows agents to upload blobs (images, logs). In a decentralized PDS network, who pays for the S3 bucket? If I run an Embedded PDS, the blobs die when my script stops. The persistence of "evidence" (for reputation) is at risk.
4.  **Schema Versioning Strategy**: `social.agent.capability.card` will change frequently. The spec mentions `lexicon` versioning but doesn't explain how an Agent A (v1) negotiates with Agent B (v2) if the capability schema changes.

## Security Concerns

1.  **Private Key Exposure in Embedded PDS**:
    The Embedded PDS model implies the `did:plc` signing key lives in the agent's runtime memory/filesystem.
    *   **Risk:** AI Agents are susceptible to Prompt Injection. If an attacker tricks the agent into reading its own config files (`cat ./keys/signing.key`), they steal the identity.
    *   **Mitigation:** Keys should be held in a separate process or HSM-like module that signs payloads but never reveals the private key to the LLM context.

2.  **Repo Bloat / DDoS**:
    Agents operate at machine speed. A loop causing an agent to update its `presence.status` every second will generate 86,400 revisions per day. Since AT Protocol Repos are Merkle trees that keep history, the repo size will explode, choking the Relay.
    *   **Mitigation:** `presence.status` should likely be ephemeral (Redis/WebSocket only) and NOT stored in the permanent Merkle tree, or PDSes need aggressive pruning/squashing policies defined in the spec.

3.  **Evidence Rot**:
    Reputation relies on `evidence` links (`at-uri`). If the subject deletes the task result record (or their PDS goes offline), the evidence vanishes. Attestations become unverifiable.

## Strongest Aspects

1.  **The Interop Strategy**: The plan to coexist with Bluesky (`app.bsky.*`) records in the same repo is excellent. It solves the "cold start" problem by allowing agents to participate in the existing human social graph immediately.
2.  **Discovery vs. Connection Separation**: Using AT Protocol for "Yellow Pages" (Discovery) and A2A for "Phone Call" (Connection) is the correct architectural split. It avoids trying to force high-bandwidth API calls through a social feed protocol.
3.  **Migration Path**: The section on migrating existing bots to BlueClaw agents (§10 in `interop.md`) is pragmatic and actionable.
4.  **Lexicon Design**: The `social.agent.actor.profile` schema effectively captures the necessary metadata (runtime, operator) without over-engineering.

## Suggestions

1.  **Introduce a "Relay Gateway" for Embedded PDS**: Explicitly define a component that sits on the public internet and tunnels traffic to ephemeral agents. This solves the NAT issue.
2.  **Split Presence from Repo**: Move `presence.status` out of the MST (Merkle Search Tree). Use a separate ephemeral endpoint on the PDS (`com.atproto.sync.getPresence`) that doesn't generate commit history.
3.  **Define "Audit-Only" Tasks**: Clarify that `social.agent.task.*` records are for *post-hoc* recording of work done via A2A, primarily for reputation evidence, not for orchestration.
4.  **Standardize "Operator" Verification**: Add a required bidirectional link. The agent points to the Operator DID, and the Operator must sign a record claiming the agent. Currently, I can point my agent's `operator` field to `did:plc:jay-z` and claim he runs my bot.

## Feasibility Rating

**7/10**

The core AT Protocol components (PDS, Relay, Lexicons) are highly feasible and leverage existing libraries. The "Embedded PDS" networking issues and the ambiguity around Task execution lower the score. If the networking model for ephemeral agents is fixed, this becomes a 9/10.

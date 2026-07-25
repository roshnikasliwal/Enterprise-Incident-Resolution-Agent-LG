"""Seed content for the internal knowledge base (runbooks / postmortems).

Ships with a small, curated set of documents covering exactly the
failure modes named in the project's own example queries (Kubernetes
restarts, Kafka broker outages, slow Postgres, HTTP 500 after deploy,
Redis connectivity) so retrieval is demonstrably useful out of the box,
without requiring a real document corpus or external ingestion pipeline
to exist yet.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeedDocument:
    document_id: str
    title: str
    doc_type: str
    component: str
    content: str


SEED_DOCUMENTS: tuple[SeedDocument, ...] = (
    SeedDocument(
        document_id="kb-k8s-crashloop",
        title="Runbook: Kubernetes Pod CrashLoopBackOff / Restart Loops",
        doc_type="runbook",
        component="kubernetes",
        content=(
            "A pod repeatedly restarting (CrashLoopBackOff) is almost always one of: "
            "(1) the container process exits non-zero on startup -- check `kubectl logs "
            "<pod> --previous` for the crash reason before the restart wiped it; "
            "(2) OOMKilled -- check `kubectl describe pod` for 'OOMKilled' in the last "
            "state reason, then compare memory usage against the container's configured "
            "limit; the fix is usually raising the memory limit or fixing a leak, not "
            "just restarting; (3) a failing readiness/liveness probe with too aggressive "
            "timing, which kills otherwise-healthy slow-starting containers -- check "
            "probe `initialDelaySeconds` and `periodSeconds`; (4) a missing or invalid "
            "ConfigMap/Secret mount causing the app to fail its own startup validation. "
            "Always check `kubectl get events --sort-by=.lastTimestamp` for the ordering "
            "of what actually happened before guessing."
        ),
    ),
    SeedDocument(
        document_id="kb-kafka-broker-down",
        title="Postmortem: Kafka Broker Unavailability and Under-Replicated Partitions",
        doc_type="postmortem",
        component="kafka",
        content=(
            "When brokers report as down, first distinguish a single-broker failure "
            "(other brokers should promote new partition leaders automatically if "
            "replication factor > 1) from a cluster-wide outage (usually ZooKeeper/"
            "KRaft controller quorum loss). Symptoms of the former: under-replicated "
            "partitions climb, producers see NotLeaderForPartitionException transiently "
            "then recover. Symptoms of the latter: no broker can be elected controller, "
            "all produce/consume stalls. Root causes we've seen: disk full on the "
            "broker's log directory (Kafka does not gracefully degrade on ENOSPC), "
            "network partition between broker and controller quorum, and JVM GC pauses "
            "exceeding the zookeeper.session.timeout.ms causing a broker to be evicted "
            "from the cluster while still technically running."
        ),
    ),
    SeedDocument(
        document_id="kb-postgres-slow-queries",
        title="Runbook: PostgreSQL Slow Query / Connection Pool Exhaustion",
        doc_type="runbook",
        component="database",
        content=(
            "'Database is slow' usually decomposes into one of: query plan regression "
            "(check pg_stat_statements for mean_exec_time outliers, then EXPLAIN "
            "ANALYZE the worst offenders -- often a missing index after a schema "
            "migration), connection pool exhaustion (application threads blocked "
            "waiting for a pooled connection while the pool is maxed out and Postgres "
            "itself is idle -- check pool utilization metrics, not just DB-side "
            "metrics), lock contention (check pg_locks joined against pg_stat_activity "
            "for long-held locks blocking others), or replication lag on a read "
            "replica being queried under a stale-read assumption. Do not assume "
            "'add an index' without confirming via EXPLAIN which step is actually slow."
        ),
    ),
    SeedDocument(
        document_id="kb-redis-connectivity",
        title="Runbook: Application Cannot Connect to Redis",
        doc_type="runbook",
        component="cache",
        content=(
            "Connection refused/timeout to Redis from an application pod is typically: "
            "(1) Redis hit maxmemory with an eviction policy of noeviction and is "
            "refusing writes (reads still work) -- check `INFO memory` for "
            "used_memory vs maxmemory and `INFO stats` for evicted_keys; "
            "(2) a NetworkPolicy or security group change blocking the app-to-Redis "
            "path after a recent infra change -- correlate the incident start time "
            "against recent NetworkPolicy/SG diffs; (3) Redis exceeded maxclients and "
            "is rejecting new connections -- check `CLIENT LIST` count; (4) the "
            "client-side connection pool is exhausted on the application side (not a "
            "Redis-side problem at all) -- check the app's own pool metrics first."
        ),
    ),
    SeedDocument(
        document_id="kb-http-500-post-deploy",
        title="Postmortem: HTTP 500 Errors Immediately Following a Deployment",
        doc_type="postmortem",
        component="application",
        content=(
            "A spike of HTTP 500s starting within minutes of a deployment finishing is "
            "almost always caused by the deploy itself, not coincidence -- check for: "
            "an unapplied or partially-applied database migration the new code assumes "
            "exists, an environment variable or secret that changed shape between the "
            "old and new config, a dependency version bump with a breaking API change, "
            "or the new pods failing to fully warm up (connection pools, caches) before "
            "receiving production traffic if the rollout strategy doesn't gate on "
            "readiness properly. Compare the error's stack trace timestamp against the "
            "deployment's rollout completion timestamp -- if they align, roll back "
            "first and investigate the root cause after service is restored."
        ),
    ),
)

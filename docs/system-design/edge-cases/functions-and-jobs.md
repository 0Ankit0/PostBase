# Edge Cases - Functions and Jobs

| Scenario | Risk | Mitigation |
|----------|------|------------|
| Runtime backend has cold-start latency spikes | Unpredictable execution latency | Publish runtime profiles and support warm capacity where possible |
| Function invocation succeeds remotely but response times out locally | Duplicate side effects on retry | Require idempotency keys for mutating invocations |
| Scheduled job misses execution during outage | Silent business failure | Track missed schedules and replay according to policy |
| Runtime provider limits memory or execution duration differently | Hidden portability gaps | Express capability limits in compatibility profiles |
| Adapter upgrade changes log format or status mapping | Broken observability | Keep execution record schema stable and map provider-specific fields internally |

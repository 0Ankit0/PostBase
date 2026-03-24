# Edge Cases - Storage and File Providers

| Scenario | Risk | Mitigation |
|----------|------|------------|
| Provider exposes eventual consistency for object listing | Missing files in immediate read-after-write scenarios | Use metadata-backed listing and document consistency semantics |
| Signed URL behavior differs between providers | Download/upload flows break | Normalize facade-level signed access contract and validate adapter compliance |
| Multipart upload interrupted mid-transfer | Orphaned objects or incomplete metadata | Use resumable flow state and cleanup jobs |
| File metadata written but provider object missing | Broken references | Reconcile object existence before committing active file state |
| Storage provider migration for large buckets | Long migration windows | Support staged copy, dual-write, checksum verification, and delayed retirement |

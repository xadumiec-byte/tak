# Live acceptance

Verdict: REVISE

| Gate | Status | Detail |
|---|---|---|
| gpu | PASS | {"name": "NVIDIA A100-SXM4-80GB", "total_mib": 81920, "used_mib": 74199, "free_mib": 6954} |
| vram | PASS | {"name": "NVIDIA A100-SXM4-80GB", "total_mib": 81920, "used_mib": 74199, "free_mib": 6954} |
| service_health | PASS | {"vllm": 200, "gateway": 200, "research": 200, "embedding": 200, "reranker": 200, "sandbox": 200, "crawler": 200, "qdrant": 200, "searxng": 200, "open-webui": 200} |
| models | NOT TESTED | "Not executed" |
| completion | NOT TESTED | "Not executed" |
| streaming | NOT TESTED | "Not executed" |
| json_response | NOT TESTED | "Not executed" |
| concurrency | NOT TESTED | "Not executed" |
| execute_code | NOT TESTED | "Not executed" |
| sandbox_exception | NOT TESTED | "Not executed" |
| sandbox_timeout | NOT TESTED | "Not executed" |
| sandbox_output_limit | NOT TESTED | "Not executed" |
| sandbox_network | NOT TESTED | "Not executed" |
| sandbox_filesystem | NOT TESTED | "Not executed" |
| sandbox_child_cleanup | NOT TESTED | "Not executed" |
| research_lifecycle | NOT TESTED | "Not executed" |
| sandbox_memory | NOT TESTED | "Not executed" |
| sandbox_process_limit | NOT TESTED | "Not executed" |
| research_failure | NOT TESTED | "Not executed" |
| research_cancel | NOT TESTED | "Not executed" |
| hybrid_rag | NOT TESTED | "Not executed" |
| citations | NOT TESTED | "Not executed" |
| tool_execute_code | NOT TESTED | "Not executed" |
| tool_submit_research | NOT TESTED | "Not executed" |
| tool_research_status | NOT TESTED | "Not executed" |
| context_8K | NOT TESTED | "Not executed" |
| context_16K | NOT TESTED | "Not executed" |
| context_32K | NOT TESTED | "Not executed" |
| benchmark | NOT TESTED | "Not executed" |
| restart | NOT TESTED | "Not executed" |
| gpu_configuration_matrix | NOT TESTED | "Not executed" |
| prompt_injection | NOT TESTED | "Not executed" |
| agent_roundtrip | NOT TESTED | "Not executed" |
| redis_crash_recovery | PASS | {"status": "PASS", "lease_ms": 120000, "docker_before": {"container_id": "b78612d22a5b4ded6a9caf8338d4700a15448c03813ad70d806b1aafa2901e84", "started_at": "2026-10-07T16:12:58.407446047Z", "restart_count": 0}, "redis_before": "3b1afc8fa26c9ebafff097d883c29f4610e90aa3", "redis_version": "7.4.11", "job_id": "f5a7f99a-3357-4c05-9c6b-511cc8f8a4ae", "phase": "DONE", "aof_barrier": [1, 0], "original_attempt": 1, "entry_id": "1791390324766-0", "redis_fault": {"container_id": "b78612d22a5b4ded6a9caf8338d4700a15448c03813ad70d806b1aafa2901e84", "started_at": "2026-10-07T16:12:58.407446047Z", "restart_count": 0, "fault": "Docker SIGKILL", "process_recovery": "explicit supervised service restart"}, "red |

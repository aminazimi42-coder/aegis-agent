Enterprise Infrastructure Notes
==============================

This folder holds lightweight pointers for deploying the Aegis Agent platform
in enterprise environments. For production, replace the simple `docker-compose`
with Helm charts, Terraform modules, and a managed KMS/HSM-backed key store.

Quick starters:
- Use Kubernetes with PodDisruptionBudgets and HorizontalPodAutoscaler.
- Replace `.kms/master.key` with a Vault HSM-wrapped KEK.
- Add Prometheus + Alertmanager for self-healing alerts.

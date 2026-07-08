#!/usr/bin/env bash
# Reboot sonrası Cilium bpffs bərpası — k3d node-ları restart olunanda mount itir
set -uo pipefail

echo ">> bpffs mount yoxlanılır və bərpa olunur..."
for node in $(docker ps --format '{{.Names}}' | grep k3d-sentinel); do
  echo "   - $node"
  # Artıq mounted-dırsa xəta verməsin
  docker exec "$node" sh -c 'mountpoint -q /sys/fs/bpf || mount bpffs -t bpf /sys/fs/bpf'
  docker exec "$node" mount --make-shared /sys/fs/bpf 2>/dev/null || true
done

echo ">> Cilium pod-ları təzələnir..."
kubectl -n kube-system delete pod -l k8s-app=cilium

echo ">> Gözlənilir..."
kubectl -n kube-system rollout status ds/cilium --timeout=180s

echo ">> Status:"
cilium status --wait

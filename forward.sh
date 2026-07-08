#!/bin/bash
# Sentinel Platform - bütün servisləri port-forward edir

echo "🚀 Sentinel servislərini açıram..."

# Köhnə port-forward-ları təmizlə
pkill -f "kubectl port-forward" 2>/dev/null
sleep 2

# Servisləri arxa planda aç
kubectl port-forward -n monitoring svc/grafana 3000:80 > /dev/null 2>&1 &
echo "  ✅ Grafana       → http://localhost:3000"

kubectl port-forward -n argocd svc/argocd-server 8090:443 > /dev/null 2>&1 &
echo "  ✅ ArgoCD        → https://localhost:8090"

kubectl port-forward -n sentinel svc/risk-engine 8000:8000 > /dev/null 2>&1 &
echo "  ✅ Risk Engine   → http://localhost:8000/docs"

kubectl port-forward -n redpanda svc/redpanda-console 8081:8080 > /dev/null 2>&1 &
echo "  ✅ Redpanda      → http://localhost:8081"

echo ""
echo "Hamısı açıldı! Dayandırmaq üçün: ./stop-forward.sh"
echo "Loglar gizlədilir. Proseslər arxa planda işləyir."

# NodePort dəyişiklikləri — mövcud fayllarda ediləcək düzəlişlər

## 1. Grafana — platform/grafana/values.yaml (əlavə et)
```yaml
service:
  type: NodePort
  nodePort: 30300
```

## 2. ArgoCD — Helm install/upgrade zamanı values
```yaml
server:
  service:
    type: NodePort
    nodePorts:
      http: 30090
```
Bootstrap zamanı:
```bash
helm install argocd argo/argo-cd -n argocd --create-namespace \
  --set server.service.type=NodePort \
  --set server.service.nodePorts.http=30090
```

## 3. Risk Engine — risk-engine/k8s-deploy.yaml içindəki Service
```yaml
apiVersion: v1
kind: Service
metadata:
  name: risk-engine
  namespace: sentinel
spec:
  type: NodePort        # ClusterIP → NodePort
  selector:
    app: risk-engine
  ports:
    - port: 8000
      targetPort: 8000
      nodePort: 30800
```

## 4. Vector — local/k3d/vector-nodeport.yaml (dəyişməz, artıq 30514)

## Yoxlama (cluster qalxandan sonra)
```bash
curl -s localhost:8000/health          # Risk Engine
curl -s localhost:3000/api/health      # Grafana
curl -sk localhost:8090                # ArgoCD
# Hubble UI: brauzerdə http://localhost:12000
# PA tərəfdən EDL: http://192.168.6.26:8000/blocklist?window=10080
```

## ⚠️ Qeyd
- forward.sh artıq LAZIM DEYİL (yalnız Redpanda schema registry 8081 lazım olsa saxla)
- PA EDL URL-i DƏYİŞMİR — port-forward yox, indi daimi NodePort
- Laptop firewall-da (ufw varsa) 514/udp, 8000/tcp açıq olmalıdır

## Kubernetes

### create namespace
```bash
kubectl apply -f namespace/lattice-cast.yaml
```

### apply secrets and configmaps
```bash
kubectl apply -f secrets/
kubectl apply -f configmaps/
```

### prepare for https

use ssl key, pem
```bash
kubectl create secret tls yourdomain-tls-secret \
  --key yourdomain.com.key \
  --cert yourdomain.com.pem \
  -n lattice-cast
```

in ```vite.config.ts``` add yourdomain
```javascript
allowedHosts: [
    'localhost',
    '127.0.0.1',
    'yourdomain.com',
],
```

### build and push to local registry
```bash
docker compose build
docker tag lattice-cast-frontend:latest 127.0.0.1:7000/lattice-cast-frontend:latest
docker push 127.0.0.1:7000/lattice-cast-frontend:latest
docker tag lattice-cast-backend:latest 127.0.0.1:7000/lattice-cast-backend:latest
docker push 127.0.0.1:7000/lattice-cast-backend:latest
```

### deploy by k8s
```bash
kubectl create -f .
```

### Debug
restart:
```bash
kubectl rollout restart deployment/frontend-deployment -n lattice-cast
kubectl rollout restart deployment/backend-deployment -n lattice-cast

```

local dev or test
```bash
kubectl port-forward service/frontend-service 3000:3000 -n lattice-cast
kubectl port-forward service/backend-service 5000:5000 -n lattice-cast
```

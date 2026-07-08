#!/bin/bash
echo "🛑 Port-forward-ları dayandırıram..."
pkill -f "kubectl port-forward"
echo "Dayandırıldı."

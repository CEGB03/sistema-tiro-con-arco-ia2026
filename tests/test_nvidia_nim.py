import os
import requests
import json

# 1. Cargar .env
if os.path.exists(".env"):
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

api_key = os.environ.get("NVIDIA_API_KEY", "").strip()

if not api_key:
    print("❌ Error: No se encontró NVIDIA_API_KEY en .env")
    exit(1)

print(f"🔑 API Key cargada: {api_key[:12]}...\n")

url = "https://integrate.api.nvidia.com/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# Candidatos multimodales / de visión en NVIDIA NIM
candidate_models = [
    "meta/llama-3.2-11b-vision-instruct",
    "meta/llama-3.2-90b-vision-instruct",
    "microsoft/phi-3.5-vision-instruct",
    "qwen/qwen2-vl-72b-instruct",
    "nvidia/neva-22b",
    "google/paligemma-7b-vc-224"
]

print("🔍 Verificando modelos multimodales activos en NVIDIA NIM...\n")

active_models = []

for model in candidate_models:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Responde 'OK' si este modelo está disponible."
            }
        ],
        "temperature": 0.1,
        "max_tokens": 16
    }
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"✅ [200 OK] Modelo ACTIVO: {model}")
            active_models.append(model)
        else:
            print(f"❌ [{resp.status_code}] {model}")
    except Exception as e:
        print(f"⚠️ Error de red con {model}: {e}")

print("\n" + "="*50)
if active_models:
    print(f"🎉 Modelos activos para tu Agente 2 ({len(active_models)}):")
    for m in active_models:
        print(f"  - {m}")
else:
    print("⚠️ Ningún modelo de la lista devolvió 200 OK.")
print("="*50)
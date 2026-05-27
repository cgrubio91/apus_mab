import requests
import time

def test_webhook():
    url = "http://localhost:8001/whatsapp_webhook"
    
    # Test 1: Authorized user, simple greeting
    print("\n🧪 Test 1: Saludo de usuario autorizado")
    data = {
        "From": "whatsapp:+573507698187",
        "Body": "Hola"
    }
    try:
        response = requests.post(url, data=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 2: Authorized user, query
    print("\n🧪 Test 2: Consulta de usuario autorizado")
    data = {
        "From": "whatsapp:+573507698187",
        "Body": "dame el precio del concreto de 3000 psi"
    }
    try:
        response = requests.post(url, data=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 3: Unauthorized user
    print("\n🧪 Test 3: Usuario no autorizado")
    data = {
        "From": "whatsapp:+1234567890",
        "Body": "Hola"
    }
    try:
        response = requests.post(url, data=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    # Wait for server to start
    print("⏳ Esperando a que el servidor inicie...")
    time.sleep(5)
    test_webhook()

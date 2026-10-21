import time
import random
import requests
import os
from prometheus_client import start_http_server, Gauge, Counter

def generate_sensor_data():
    return {
        'temperature': random.gauss(25, 5),
        'humidity': random.gauss(50, 10),
        'co2': random.gauss(400, 50),
        'vibration': random.gauss(0.1, 0.05)
    }

def inject_anomaly(data):
    if random.random() < 0.05:
        data['temperature'] += random.uniform(10, 20)
        data['co2'] += random.uniform(200, 500)
    return data

def save_to_db(agent_id, data):
    import psycopg2
    try:
        conn = psycopg2.connect(
            host="postgres",
            database="iot_anomaly",
            user="iot",
            password="iot123"
        )
        cur = conn.cursor()
        is_anomaly = data['temperature'] > 35 or data['co2'] > 700
        cur.execute("""
            INSERT INTO iot_data (agent_id, temperature, humidity, co2, vibration, is_anomaly)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (agent_id, data['temperature'], data['humidity'], data['co2'], data['vibration'], is_anomaly))
        conn.commit()
        cur.close()
        conn.close()
        return is_anomaly
    except Exception as e:
        print(f"DB error: {e}")
        return False

AGENT_ID = os.getenv("AGENT_ID", "agentX")
COORDINATOR_URL = os.getenv("COORDINATOR_URL", "http://iot_coordinator:8001")

anomaly_score = Gauge('anomaly_score', 'Local anomaly score', ['agent'])
anomalies_detected = Counter('anomalies_detected_total', 'Total anomalies detected', ['agent'])

def compute_anomaly_score(data):
    score = 0
    if data['temperature'] > 30:
        score += (data['temperature'] - 30) / 10
    if data['co2'] > 600:
        score += (data['co2'] - 600) / 200
    if data['vibration'] > 0.2:
        score += (data['vibration'] - 0.2) * 5
    return min(score, 1.0)

def participate_in_auction(score):
    try:
        resp = requests.post(f'{COORDINATOR_URL}/bid', json={
            "agent_id": AGENT_ID,
            "score": score
        }, timeout=1)
        if resp.status_code == 200:
            return resp.json().get("winner") == AGENT_ID
        return False
    except Exception as e:
        print(f"Auction error: {e}")
        return False

def run_agent():
    start_http_server(8000)
    print(f"Agent {AGENT_ID} started, metrics on port 8000")
    while True:
        try:
            raw_data = generate_sensor_data()
            raw_data = inject_anomaly(raw_data)
            score = compute_anomaly_score(raw_data)
            anomaly_score.labels(agent=AGENT_ID).set(score)
            
            is_winner = participate_in_auction(score)
            if is_winner:
                anomalies_detected.labels(agent=AGENT_ID).inc()
                print(f"{AGENT_ID} ВЫИГРАЛ аукцион! Аномалия: {score:.2f}")
            
            save_to_db(AGENT_ID, raw_data)
            time.sleep(3)
        except Exception as e:
            print(f"Error in agent loop: {e}")
            time.sleep(3)

if __name__ == "__main__":
    run_agent()

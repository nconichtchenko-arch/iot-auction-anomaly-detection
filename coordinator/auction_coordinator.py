from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel
import time
import threading
import psycopg2
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Gauge, Counter, CollectorRegistry

registry = CollectorRegistry()
winner_gauge = Gauge('auction_winner', 'Winning agent in last auction', registry=registry)
auction_duration = Gauge('auction_duration_seconds', 'Auction duration', registry=registry)
total_bids = Counter('total_bids_received', 'Total bids received', registry=registry)
auction_rounds = Counter('auction_rounds_completed', 'Auction rounds completed', registry=registry)

app = FastAPI()

class Bid(BaseModel):
    agent_id: str
    score: float

bids = {}
auction_round = 0

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

@app.post("/bid")
def place_bid(bid: Bid):
    global bids
    bids[bid.agent_id] = bid.score
    total_bids.inc()
    return {"status": "received", "winner": None}

@app.get("/health")
def health():
    return {"status": "alive", "round": auction_round, "bids": len(bids)}

def run_auction():
    global bids, auction_round
    while True:
        start_time = time.time()
        if bids:
            winner = max(bids.items(), key=lambda x: x[1])
            print(f"Раунд {auction_round}: Победитель {winner[0]} со счётом {winner[1]:.2f}")
            try:
                conn = psycopg2.connect(host="postgres", database="iot_anomaly", user="iot", password="iot123")
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO auction_log (round, winner_agent, bid_value)
                    VALUES (%s, %s, %s)
                """, (auction_round, winner[0], winner[1]))
                conn.commit()
                cur.close()
                conn.close()
            except Exception as e:
                print(f"DB error: {e}")
            
            try:
                winner_num = int(winner[0][-1]) if winner[0][-1].isdigit() else 0
                winner_gauge.set(winner_num)
            except:
                winner_gauge.set(0)
            
            auction_rounds.inc()
            bids = {}
            auction_round += 1
            auction_duration.set(time.time() - start_time)
        
        time.sleep(10)

if __name__ == "__main__":
    threading.Thread(target=run_auction, daemon=True).start()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

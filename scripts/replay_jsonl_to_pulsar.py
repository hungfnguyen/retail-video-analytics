import time
import os
import pulsar
from pathlib import Path

# Configuration
# Kết nối tới Pulsar standalone từ Windows host
PULSAR_SERVICE_URL = os.getenv("PULSAR_SERVICE_URL", "pulsar://127.0.0.1:6650")
# Must match the topic created in init-topics.sh: persistent://retail/metadata/events
TOPIC_NAME = "persistent://retail/metadata/events"
JSONL_FILE = Path(__file__).resolve().parent.parent / "data/metadata/video.jsonl"
FPS = 30.0  # Frames per second to simulate

def main():
    print(f"Connecting to Pulsar at {PULSAR_SERVICE_URL}...")
    client = pulsar.Client(PULSAR_SERVICE_URL)
    producer = client.create_producer(TOPIC_NAME)

    if not JSONL_FILE.exists():
        print(f"Error: File not found at {JSONL_FILE}")
        return

    print(f"Replaying data from {JSONL_FILE} to topic '{TOPIC_NAME}'...")
    
    try:
        with open(JSONL_FILE, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                # Send to Pulsar
                producer.send(line.encode('utf-8'))
                
                if line_num % 100 == 0:
                    print(f"Sent {line_num} frames...")

                # Simulate streaming delay
                time.sleep(1.0 / FPS)

        print(f"Finished replaying {line_num} frames.")

    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        producer.close()
        client.close()
        print("Pulsar client closed.")

if __name__ == "__main__":
    main()

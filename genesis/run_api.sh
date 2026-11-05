#!/bin/bash
cd /home/alieninc/genesis
exec uvicorn api:app --host 127.0.0.1 --port 8001

import asyncio
import websockets
import json

async def test():
    uri = 'ws://localhost:8000/ws'
    print(f'Connecting to {uri}...')
    async with websockets.connect(uri) as ws:
        print('Connected!')
        msg = await ws.recv()
        data = json.loads(msg)
        print(f'Received from backend: {data}')
        print('SUCCESS - AlphaSurface pipeline is alive')

asyncio.run(test())

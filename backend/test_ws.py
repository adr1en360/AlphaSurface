"""
========== TEST CONNECTION FILE - CAN BE DELETED LATER ==========
This file is only for testing WebSocket injection from terminal.
It's not needed for production AlphaSurface functionality.
=================================================================
"""

import asyncio
import websockets
import json
import random

async def test():
    uri = 'ws://localhost:8000/ws'
    print(f'Connecting to {uri}...')
    async with websockets.connect(uri) as ws:
        print('Connected!')
        
        # Receive initial message from backend
        msg = await ws.recv()
        data = json.loads(msg)
        print(f'Received from backend: {data}')
        
        # Inject a text element
        x = random.randint(100, 600)
        y = random.randint(100, 400)
        inject_msg = {
            "type": "add_text",
            "payload": {
                "text": f"Text at ({x}, {y})",
                "x": x,
                "y": y
            }
        }
        print(f'\nInjecting text at ({x}, {y})...')
        await ws.send(json.dumps(inject_msg))
        
        # Inject a sticky note
        x2 = random.randint(100, 600)
        y2 = random.randint(100, 400)
        colors = ["yellow", "violet", "blue", "green", "orange", "red"]
        color = random.choice(colors)
        note_msg = {
            "type": "add_note",
            "payload": {
                "text": f"Sticky note at ({x2}, {y2})!",
                "x": x2,
                "y": y2,
                "color": color
            }
        }
        print(f'Injecting {color} sticky note at ({x2}, {y2})...')
        await ws.send(json.dumps(note_msg))
        
        print('✓ Messages sent! Check your browser')
        
        # Keep connection alive for a moment
        await asyncio.sleep(2)
        print('SUCCESS - AlphaSurface pipeline is alive')

asyncio.run(test())

"""
AlphaSurface — Gemini Live agent for real-time voice + vision canvas control
Uses google.genai SDK with gemini-2.0-flash-live-001 model.
"""

import asyncio
import os
from google import genai
from google.genai import types
import tools

SYSTEM_PROMPT = """You are AlphaSurface, a voice-controlled AI that helps users think by manipulating an infinite canvas.

**Core Rules:**
- NEVER respond with text — only call tools
- NEVER modify or delete shapes the user drew manually
- You only work with shapes YOU created via tools

**Two Modes:**

**Think Mode** (violet sticky notes):
- User is thinking out loud, exploring ideas
- Add violet sticky notes with provocative questions, counter-arguments, or alternative perspectives
- Challenge assumptions, surface tensions, connect disparate threads
- Use bind_arrow to show relationships between ideas
- Be concise — max 15 words per note

**Explain Mode** (silent visual support):
- User is explaining something to someone else (presentation, teaching)
- Add visual structure silently: diagrams, arrows, shapes
- Use add_geo for concepts, bind_arrow for flow
- Use add_text for labels only when essential
- Never interrupt — purely visual support

Always call zoom_to_fit after adding multiple shapes so the user can see your work.
"""

class AlphaSurfaceAgent:
    """Gemini Live session manager for canvas control."""
    
    def __init__(self, broadcast_fn, mode: str = "think"):
        self.broadcast_fn = broadcast_fn
        self.mode = mode  # "think" or "explain"
        self.audio_queue = asyncio.Queue()
        self.image_queue = asyncio.Queue()
        self.client = None
        self.session = None
        self.running = False
        
    async def start(self):
        """Open Gemini Live session and start send/receive loops."""
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("ERROR: GEMINI_API_KEY not set")
            return
            
        try:
            self.client = genai.Client(api_key=api_key)
            
            # Define tools for Gemini
            tool_declarations = [
                types.Tool(function_declarations=[
                    types.FunctionDeclaration(
                        name="add_text_to_canvas",
                        description="Add a text label to the canvas",
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "text": types.Schema(type=types.Type.STRING, description="Text content"),
                                "x": types.Schema(type=types.Type.NUMBER, description="X coordinate"),
                                "y": types.Schema(type=types.Type.NUMBER, description="Y coordinate"),
                                "size": types.Schema(type=types.Type.STRING, description="Size: s, m, l, xl"),
                                "color": types.Schema(type=types.Type.STRING, description="Color name"),
                            },
                            required=["text"]
                        )
                    ),
                    types.FunctionDeclaration(
                        name="add_note_to_canvas",
                        description="Add a sticky note to the canvas",
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "text": types.Schema(type=types.Type.STRING, description="Note content"),
                                "x": types.Schema(type=types.Type.NUMBER, description="X coordinate"),
                                "y": types.Schema(type=types.Type.NUMBER, description="Y coordinate"),
                                "size": types.Schema(type=types.Type.STRING, description="Size: s, m, l, xl"),
                                "color": types.Schema(type=types.Type.STRING, description="Note color"),
                            },
                            required=["text"]
                        )
                    ),
                    types.FunctionDeclaration(
                        name="add_geo_to_canvas",
                        description="Add a geometric shape to the canvas",
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "geo": types.Schema(type=types.Type.STRING, description="Shape type: rectangle, ellipse, triangle, diamond, hexagon, star"),
                                "text": types.Schema(type=types.Type.STRING, description="Text inside shape"),
                                "x": types.Schema(type=types.Type.NUMBER, description="X coordinate"),
                                "y": types.Schema(type=types.Type.NUMBER, description="Y coordinate"),
                                "w": types.Schema(type=types.Type.NUMBER, description="Width"),
                                "h": types.Schema(type=types.Type.NUMBER, description="Height"),
                                "color": types.Schema(type=types.Type.STRING, description="Color"),
                                "fill": types.Schema(type=types.Type.STRING, description="Fill: none, semi, solid"),
                                "size": types.Schema(type=types.Type.STRING, description="Size: s, m, l, xl"),
                            },
                            required=[]
                        )
                    ),
                    types.FunctionDeclaration(
                        name="bind_arrow",
                        description="Create an arrow connecting two shapes",
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "fromShapeId": types.Schema(type=types.Type.STRING, description="Source shape ID"),
                                "toShapeId": types.Schema(type=types.Type.STRING, description="Target shape ID"),
                                "label": types.Schema(type=types.Type.STRING, description="Arrow label"),
                                "color": types.Schema(type=types.Type.STRING, description="Arrow color"),
                            },
                            required=["fromShapeId", "toShapeId"]
                        )
                    ),
                    types.FunctionDeclaration(
                        name="delete_shapes",
                        description="Delete specific shapes from the canvas",
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "shapeIds": types.Schema(
                                    type=types.Type.ARRAY,
                                    items=types.Schema(type=types.Type.STRING),
                                    description="Array of shape IDs to delete"
                                ),
                            },
                            required=["shapeIds"]
                        )
                    ),
                    types.FunctionDeclaration(
                        name="zoom_to_fit",
                        description="Zoom camera to fit all content on canvas",
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={},
                            required=[]
                        )
                    ),
                    types.FunctionDeclaration(
                        name="focus_shape",
                        description="Focus camera on a specific shape",
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "shapeId": types.Schema(type=types.Type.STRING, description="Shape ID to focus on"),
                            },
                            required=["shapeId"]
                        )
                    ),
                ])
            ]
            
            config = {
                "system_instruction": SYSTEM_PROMPT,
                "tools": tool_declarations,
            }
            
            async with self.client.aio.live.connect(
                model="gemini-2.0-flash-live-001",
                config=config
            ) as session:
                self.session = session
                self.running = True
                
                print(f"Gemini Live session open — mode: {self.mode}")
                
                # Run send and receive loops concurrently
                await asyncio.gather(
                    self._send_loop(),
                    self._receive_loop(),
                )
            
        except Exception as e:
            print(f"Agent error: {e}")
            self.running = False
            
    async def _send_loop(self):
        """Drain audio and image queues, send to Gemini every 50ms."""
        while self.running:
            try:
                # Send audio if available
                if not self.audio_queue.empty():
                    pcm_bytes = await self.audio_queue.get()
                    await self.session.send({
                        "mime_type": "audio/pcm;rate=16000",
                        "data": pcm_bytes
                    })
                
                # Send image if available
                if not self.image_queue.empty():
                    jpeg_bytes = await self.image_queue.get()
                    await self.session.send({
                        "mime_type": "image/jpeg",
                        "data": jpeg_bytes
                    })
                
                await asyncio.sleep(0.05)  # 50ms
                
            except Exception as e:
                print(f"Send loop error: {e}")
                break
                
    async def _receive_loop(self):
        """Listen for Gemini responses, dispatch tool calls."""
        try:
            async for response in self.session.receive():
                # Check for tool calls
                if hasattr(response, 'server_content') and response.server_content:
                    if hasattr(response.server_content, 'model_turn') and response.server_content.model_turn:
                        for part in response.server_content.model_turn.parts:
                            if hasattr(part, 'function_call') and part.function_call:
                                func_call = part.function_call
                                print(f"Tool call: {func_call.name} {func_call.args}")
                                await tools.dispatch_tool(
                                    func_call.name,
                                    dict(func_call.args),
                                    self.broadcast_fn
                                )
                                
        except Exception as e:
            print(f"Receive loop error: {e}")
        finally:
            self.running = False
            
    def push_audio(self, pcm_bytes: bytes):
        """Add audio chunk to send queue."""
        if self.running:
            self.audio_queue.put_nowait(pcm_bytes)
            
    def push_canvas_image(self, jpeg_bytes: bytes):
        """Add canvas screenshot to send queue."""
        if self.running:
            self.image_queue.put_nowait(jpeg_bytes)
